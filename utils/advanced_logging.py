"""
Advanced logging system for Tower of Temptation PvP Statistics Discord Bot.

This module provides:
1. Multi-level logging with rotation
2. Discord webhook integration
3. Contextual logging with metadata
4. Error aggregation and deduplication
5. Performance tracking of logged operations
6. Rate limiting for log noise reduction
7. Audit trail functionality
8. Log search and filtering
"""
import logging
import logging.handlers
import os
import sys
import traceback
import asyncio
import time
import json
import re
import hashlib
from enum import Enum
from typing import Dict, List, Set, Any, Optional, Tuple, Union, Callable, cast
from datetime import datetime, timedelta
from functools import wraps
import threading
import queue

# Discord webhook client for logging critical errors
try:
    import aiohttp
except ImportError:
    aiohttp = None

# Default log settings
DEFAULT_LOG_DIR = "logs"
DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
DEFAULT_BACKUP_COUNT = 10
DEFAULT_LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
DEFAULT_LOG_LEVEL = logging.INFO

# Discord webhook settings
DISCORD_WEBHOOK_URL = os.environ.get("LOG_WEBHOOK_URL")
DISCORD_RATE_LIMIT = 5  # Max messages per minute

# Error aggregation
ERROR_CACHE = {}  # hash -> {count, last_time, traceback}
ERROR_CACHE_TTL = 3600  # 1 hour
ERROR_RATE_LIMIT = 3  # Max same error per hour

# Audit trail settings
AUDIT_LOG_ENABLED = True
AUDIT_LOG_LEVEL = logging.INFO
AUDIT_TARGETS = ["command", "admin", "moderation", "data", "connection"]


class LogLevel(Enum):
    """Extended log levels"""
    TRACE = 5
    DEBUG = 10
    INFO = 20
    NOTICE = 25  # Between INFO and WARNING
    WARNING = 30
    ERROR = 40
    CRITICAL = 50
    ALERT = 55  # Between CRITICAL and EMERGENCY
    EMERGENCY = 60


class ContextAdapter(logging.LoggerAdapter):
    """Logger adapter that adds context to log messages"""
    
    def process(self, msg, kwargs):
        if 'extra' not in kwargs:
            kwargs['extra'] = {}
            
        # Add context from adapter
        if hasattr(self, 'context') and self.context:
            for key, value in self.context.items():
                if key not in kwargs['extra']:
                    kwargs['extra'][key] = value
                    
        return msg, kwargs


class RateLimitedLogFilter(logging.Filter):
    """Filter that rate limits log messages"""
    
    def __init__(self, rate: int = 5, period: int = 60):
        """Initialize filter
        
        Args:
            rate: Maximum number of identical messages per period
            period: Time period in seconds
        """
        super().__init__()
        self.rate = rate
        self.period = period
        self.messages = {}  # message -> (count, first_time)
        
    def filter(self, record):
        """Filter log record
        
        Args:
            record: Log record
            
        Returns:
            bool: Whether to include the record
        """
        # Always allow non-duplicated messages
        message = record.getMessage()
        now = time.time()
        
        # Check if message is in cache
        if message in self.messages:
            count, first_time = self.messages[message]
            
            # Reset if period has passed
            if now - first_time > self.period:
                self.messages[message] = (1, now)
                return True
                
            # Increment count and rate limit
            count += 1
            self.messages[message] = (count, first_time)
            
            if count > self.rate:
                # Allow final message with count
                if count == self.rate + 1:
                    record.msg = f"{message} (rate limited, repeated {count} times)"
                    return True
                return False
        else:
            # New message
            self.messages[message] = (1, now)
            
        return True


class SuccessFilter(logging.Filter):
    """Filter that excludes successful operation logs"""
    
    def __init__(self):
        """Initialize filter"""
        super().__init__()
        
        # Patterns for successful operations to filter out
        self.success_patterns = [
            r"Successfully processed .* lines from CSV file",
            r"Download completed successfully",
            r"CSV file .* processed successfully",
            r"Found \d+ files in directory",
            r"Processed event successfully",
            r"Operation .* succeeded in \d+\.\d+s"
        ]
        
        # Compile patterns
        self.compiled_patterns = [re.compile(pattern) for pattern in self.success_patterns]
        
    def filter(self, record):
        """Filter log record
        
        Args:
            record: Log record
            
        Returns:
            bool: Whether to include the record
        """
        # Always keep errors and warnings
        if record.levelno >= logging.WARNING:
            return True
            
        # Check message against success patterns
        message = record.getMessage()
        for pattern in self.compiled_patterns:
            if pattern.search(message):
                return False  # Filter out successful operation
                
        return True  # Keep other messages


class DiscordWebhookHandler(logging.Handler):
    """Log handler that sends messages to Discord webhook"""
    
    def __init__(self, webhook_url: str, level=logging.ERROR, rate_limit: int = 5, 
                max_queue: int = 100):
        """Initialize handler
        
        Args:
            webhook_url: Discord webhook URL
            level: Minimum log level to send
            rate_limit: Maximum messages per minute
            max_queue: Maximum queue size for webhook messages
        """
        super().__init__(level)
        self.webhook_url = webhook_url
        self.rate_limit = rate_limit
        self.last_messages = []  # (time, message)
        self.queue = queue.Queue(maxsize=max_queue)
        self.session = None
        self.worker = None
        self.shutdown_flag = False
        
        # Start worker thread
        self.start_worker()
        
    def start_worker(self):
        """Start worker thread to process webhook messages"""
        if not self.worker or not self.worker.is_alive():
            self.worker = threading.Thread(target=self._worker_thread, daemon=True)
            self.worker.start()
            
    def _worker_thread(self):
        """Worker thread to send webhook messages"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def run_worker():
            # Create session
            self.session = aiohttp.ClientSession()
            
            while not self.shutdown_flag:
                try:
                    # Get message from queue with timeout
                    try:
                        message, level, record_time = self.queue.get(timeout=1)
                    except queue.Empty:
                        await asyncio.sleep(0.1)
                        continue
                        
                    # Check rate limit
                    now = time.time()
                    self.last_messages = [msg for msg in self.last_messages 
                                         if now - msg[0] < 60]  # Keep last minute
                                         
                    if len(self.last_messages) >= self.rate_limit:
                        # Rate limited, add summary message
                        if len(self.last_messages) == self.rate_limit:
                            await self._send_webhook_message(
                                "💡 **Rate limit reached, logging paused for 60 seconds**",
                                level, record_time
                            )
                        continue
                        
                    # Send message
                    await self._send_webhook_message(message, level, record_time)
                    self.last_messages.append((now, message))
                    
                    # Mark as done
                    self.queue.task_done()
                    
                except Exception as e:
                    print(f"Error in webhook worker: {e}")
                    await asyncio.sleep(5)
                    
            # Clean up
            if self.session is not None:
                await self.session.close()
                
        loop.run_until_complete(run_worker())
        loop.close()
        
    async def _send_webhook_message(self, message: str, level: int, record_time: float):
        """Send message to Discord webhook
        
        Args:
            message: Message to send
            level: Log level
            record_time: Record timestamp
        """
        if not self.session or not aiohttp:
            return
            
        # Format embed
        color = 0x3498DB  # Blue (INFO)
        if level >= logging.CRITICAL:
            color = 0xE74C3C  # Red
        elif level >= logging.ERROR:
            color = 0xE67E22  # Orange
        elif level >= logging.WARNING:
            color = 0xF1C40F  # Yellow
            
        timestamp = datetime.fromtimestamp(record_time).isoformat()
        
        payload = {
            "embeds": [{
                "title": f"Log Entry: {logging.getLevelName(level)}",
                "description": message,
                "color": color,
                "timestamp": timestamp
            }]
        }
        
        try:
            async with self.session.post(self.webhook_url, json=payload) as response:
                if response.status >= 400:
                    text = await response.text()
                    print(f"Error sending to webhook: {response.status} - {text}")
        except Exception as e:
            print(f"Failed to send to Discord webhook: {e}")
            
    def emit(self, record):
        """Emit log record
        
        Args:
            record: Log record
        """
        if not aiohttp or not self.webhook_url:
            return
            
        try:
            # Format message
            message = self.format(record)
            
            # Add to queue
            try:
                self.queue.put_nowait((message, record.levelno, record.created))
            except queue.Full:
                pass
                
        except Exception as e:
            print(f"Error in Discord webhook handler: {e}")
            
    def close(self):
        """Clean up resources"""
        self.shutdown_flag = True
        if self.worker and self.worker.is_alive():
            self.worker.join(timeout=5)
        super().close()


class ErrorAggregator(logging.Handler):
    """Handler that aggregates similar errors"""
    
    def __init__(self, level=logging.ERROR, capacity: int = 100):
        """Initialize handler
        
        Args:
            level: Minimum log level to aggregate
            capacity: Maximum number of distinct errors to track
        """
        super().__init__(level)
        self.capacity = capacity
        
    def emit(self, record):
        """Emit log record
        
        Args:
            record: Log record
        """
        if record.exc_info is None:
            return
            
        try:
            # Get exception info
            exc_type, exc_value, exc_tb = record.exc_info
            tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
            
            # Create hash of traceback
            hash_key = hashlib.md5(tb_str.encode()).hexdigest()
            
            # Clean up old entries
            now = time.time()
            for key in list(ERROR_CACHE.keys()):
                if now - ERROR_CACHE[key]["last_time"] > ERROR_CACHE_TTL:
                    del ERROR_CACHE[key]
                    
            # Check capacity
            if len(ERROR_CACHE) >= self.capacity and hash_key not in ERROR_CACHE:
                # Remove oldest entry
                oldest_key = min(ERROR_CACHE.keys(), key=lambda k: ERROR_CACHE[k]["last_time"])
                del ERROR_CACHE[oldest_key]
                
            # Update or add entry
            if hash_key in ERROR_CACHE:
                ERROR_CACHE[hash_key]["count"] += 1
                ERROR_CACHE[hash_key]["last_time"] = now
            else:
                ERROR_CACHE[hash_key] = {
                    "count": 1,
                    "first_time": now,
                    "last_time": now,
                    "traceback": tb_str,
                    "message": record.getMessage(),
                    "level": record.levelno
                }
                
        except Exception as e:
            print(f"Error in error aggregator: {e}")


class AuditLogger:
    """Logger for tracking user actions and system events"""
    
    def __init__(self, logger_name: str = "audit", log_dir: str = "logs"):
        """Initialize audit logger
        
        Args:
            logger_name: Logger name
            log_dir: Log directory
        """
        self.logger = logging.getLogger(logger_name)
        
        if AUDIT_LOG_ENABLED is not None:
            # Ensure log directory exists
            os.makedirs(log_dir, exist_ok=True)
            
            # Create audit log file handler
            audit_log_file = os.path.join(log_dir, "audit.log")
            handler = logging.handlers.RotatingFileHandler(
                audit_log_file, maxBytes=DEFAULT_MAX_BYTES, backupCount=DEFAULT_BACKUP_COUNT
            )
            
            formatter = logging.Formatter(
                "%(asctime)s - %(levelname)s - %(username)s - %(guild_id)s - %(action)s - %(details)s"
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(AUDIT_LOG_LEVEL)
        
    def log_action(self, username: str, guild_id: Optional[str], action: str, 
                  details: str, level: int = logging.INFO, target: str = "system",
                  metadata: Optional[Dict[str, Any]] = None):
        """Log user action
        
        Args:
            username: User who performed the action
            guild_id: Guild ID or None
            action: Action performed
            details: Action details
            level: Log level
            target: Action target (command, admin, moderation, etc.)
            metadata: Additional metadata
        """
        if not AUDIT_LOG_ENABLED or target not in AUDIT_TARGETS:
            return
            
        # Create extra context
        extra = {
            "username": username,
            "guild_id": guild_id if guild_id is not None else "",
            "action": action,
            "details": details,
            "target": target
        }
        
        # Add metadata if provided
        if metadata is not None:
            for key, value in metadata.items():
                extra[key] = value
                
        # Log with extra context
        self.logger.log(level, f"{action}: {details}", extra=extra)
        
    def command(self, username: str, guild_id: Optional[str], command: str, 
               args: Optional[str] = None, success: bool = True):
        """Log command execution
        
        Args:
            username: User who executed the command
            guild_id: Guild ID or None
            command: Command name
            args: Command arguments
            success: Whether the command was successful
        """
        status = "succeeded" if success else "failed"
        args_str = f" with args: {args}" if args else ""
        self.log_action(
            username, guild_id, f"command_{status}", 
            f"{command}{args_str}",
            level=logging.INFO if success else logging.WARNING,
            target="command"
        )
        
    def admin_action(self, username: str, guild_id: Optional[str], action: str, target: str):
        """Log admin action
        
        Args:
            username: Admin who performed the action
            guild_id: Guild ID or None
            action: Action performed
            target: Target of the action
        """
        self.log_action(
            username, guild_id, "admin_action",
            f"{action} on {target}",
            level=logging.INFO,
            target="admin"
        )
        
    def data_change(self, username: str, guild_id: Optional[str], data_type: str, 
                  operation: str, item_id: str):
        """Log data change
        
        Args:
            username: User who made the change
            guild_id: Guild ID or None
            data_type: Type of data changed
            operation: Operation performed (create, update, delete)
            item_id: ID of the changed item
        """
        self.log_action(
            username, guild_id, "data_change",
            f"{operation} {data_type} {item_id}",
            level=logging.INFO,
            target="data"
        )
        
    def connection(self, username: str, guild_id: Optional[str], connection_type: str,
                 status: str, details: Optional[str] = None):
        """Log connection event
        
        Args:
            username: User associated with the connection
            guild_id: Guild ID or None
            connection_type: Type of connection
            status: Connection status
            details: Additional details
        """
        self.log_action(
            username, guild_id, "connection",
            f"{connection_type} {status}" + (f": {details}" if details else ""),
            level=logging.INFO,
            target="connection"
        )


class AdvancedLoggingSystem:
    """Advanced logging system with multiple handlers and features"""
    
    def __init__(self, app_name: str = "tower_of_temptation", log_dir: str = DEFAULT_LOG_DIR,
                level: int = DEFAULT_LOG_LEVEL, log_to_console: bool = True,
                log_to_file: bool = True, log_to_discord: bool = False):
        """Initialize logging system
        
        Args:
            app_name: Application name
            log_dir: Log directory
            level: Default log level
            log_to_console: Whether to log to console
            log_to_file: Whether to log to file
            log_to_discord: Whether to log critical errors to Discord
        """
        self.app_name = app_name
        self.log_dir = log_dir
        self.default_level = level
        self.root_logger = logging.getLogger()
        
        # Ensure log directory exists
        if log_to_file is not None:
            os.makedirs(log_dir, exist_ok=True)
            
        # Configure root logger
        self.root_logger.setLevel(level)
        
        # Remove existing handlers
        for handler in list(self.root_logger.handlers):
            self.root_logger.removeHandler(handler)
            
        # Add console handler if enabled
        if log_to_console is not None:
            console_handler = logging.StreamHandler()
            console_formatter = logging.Formatter(DEFAULT_LOG_FORMAT)
            console_handler.setFormatter(console_formatter)
            console_handler.setLevel(level)
            self.root_logger.addHandler(console_handler)
            
        # Add file handler if enabled
        if log_to_file is not None:
            # Main log file
            log_file = os.path.join(log_dir, f"{app_name}.log")
            file_handler = logging.handlers.RotatingFileHandler(
                log_file, maxBytes=DEFAULT_MAX_BYTES, backupCount=DEFAULT_BACKUP_COUNT
            )
            file_formatter = logging.Formatter(DEFAULT_LOG_FORMAT)
            file_handler.setFormatter(file_formatter)
            file_handler.setLevel(level)
            self.root_logger.addHandler(file_handler)
            
            # Error log file (ERROR and above)
            error_log_file = os.path.join(log_dir, f"{app_name}_error.log")
            error_handler = logging.handlers.RotatingFileHandler(
                error_log_file, maxBytes=DEFAULT_MAX_BYTES, backupCount=DEFAULT_BACKUP_COUNT
            )
            error_formatter = logging.Formatter(DEFAULT_LOG_FORMAT)
            error_handler.setFormatter(error_formatter)
            error_handler.setLevel(logging.ERROR)
            self.root_logger.addHandler(error_handler)
            
        # Add Discord webhook handler if enabled
        if log_to_discord and DISCORD_WEBHOOK_URL and aiohttp:
            discord_handler = DiscordWebhookHandler(
                DISCORD_WEBHOOK_URL, level=logging.ERROR, rate_limit=DISCORD_RATE_LIMIT
            )
            discord_formatter = logging.Formatter("%(levelname)s: %(message)s")
            discord_handler.setFormatter(discord_formatter)
            self.root_logger.addHandler(discord_handler)
            
        # Add error aggregator
        error_aggregator = ErrorAggregator(level=logging.ERROR)
        self.root_logger.addHandler(error_aggregator)
        
        # Add rate limit filter
        rate_limit_filter = RateLimitedLogFilter()
        for handler in self.root_logger.handlers:
            handler.addFilter(rate_limit_filter)
            
        # Create audit logger
        self.audit_logger = AuditLogger(logger_name=f"{app_name}.audit", log_dir=log_dir)
        
        # Log initialization
        logging.info(f"Advanced logging system initialized: {app_name}")
        
    def get_logger(self, name: str, context: Optional[Dict[str, Any]] = None):
        """Get logger with optional context
        
        Args:
            name: Logger name
            context: Optional context to add to log messages
            
        Returns:
            Logger: Logger instance
        """
        logger = logging.getLogger(name)
        
        if context is not None:
            adapter = ContextAdapter(logger, {})
            adapter.context = context
            return adapter
        
        return logger
        
    def log_performance(self, operation: str, elapsed_time: float, success: bool = True, 
                       details: Optional[str] = None, level: int = logging.DEBUG):
        """Log operation performance
        
        Args:
            operation: Operation name
            elapsed_time: Elapsed time in seconds
            success: Whether the operation was successful
            details: Additional details
            level: Log level
        """
        status = "succeeded" if success else "failed"
        message = f"Operation '{operation}' {status} in {elapsed_time:.3f}s"
        
        if details is not None:
            message += f": {details}"
            
        logging.log(level, message)
        
    def get_error_summary(self) -> List[Dict[str, Any]]:
        """Get summary of aggregated errors
        
        Returns:
            List of error summaries
        """
        result = []
        
        for hash_key, error in ERROR_CACHE.items():
            result.append({
                "count": error["count"],
                "first_time": datetime.fromtimestamp(error["first_time"]).isoformat(),
                "last_time": datetime.fromtimestamp(error["last_time"]).isoformat(),
                "message": error["message"],
                "level": logging.getLevelName(error["level"]),
                "traceback_preview": error["traceback"].split("\n")[-1]
            })
            
        return sorted(result, key=lambda x: x["count"], reverse=True)
        
    def reset_error_cache(self):
        """Clear error aggregation cache"""
        ERROR_CACHE.clear()
        logging.info("Error aggregation cache cleared")


def timed_operation(name: Optional[str] = None, level: int = logging.DEBUG):
    """Decorator to log operation timing
    
    Args:
        name: Operation name (defaults to function name)
        level: Log level
        
    Returns:
        Decorator function
    """
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            operation = name or func.__name__
            start_time = time.time()
            success = True
            
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                success = False
                raise
            finally:
                elapsed = time.time() - start_time
                logging.log(
                    level,
                    f"Operation '{operation}' {'succeeded' if success else 'failed'} in {elapsed:.3f}s"
                )
                
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            operation = name or func.__name__
            start_time = time.time()
            success = True
            
            try:
                result = func(*args, **kwargs)
                return result
            except Exception:
                success = False
                raise
            finally:
                elapsed = time.time() - start_time
                logging.log(
                    level,
                    f"Operation '{operation}' {'succeeded' if success else 'failed'} in {elapsed:.3f}s"
                )
                
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator


def init_logging(app_name: str = "tower_of_temptation", log_to_discord: bool = False, filter_success: bool = True):
    """Initialize advanced logging system
    
    Args:
        app_name: Application name
        log_to_discord: Whether to log critical errors to Discord
        filter_success: Whether to filter out successful operations
        
    Returns:
        AdvancedLoggingSystem: Logging system
    """
    logging_system = AdvancedLoggingSystem(
        app_name=app_name,
        log_to_discord=log_to_discord
    )
    
    # Add success filter if enabled
    if filter_success is not None:
        success_filter = SuccessFilter()
        for handler in logging.getLogger().handlers:
            handler.addFilter(success_filter)
            
    return logging_system