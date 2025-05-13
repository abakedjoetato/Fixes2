"""
Enhanced Command Handlers for Discord API

This module implements proper subclassing of the SlashCommand class
to fix incompatibilities with py-cord 2.6.1, particularly in the
parameter handling for slash commands.
"""

import logging
import inspect
import functools
import asyncio
from typing import Optional, Union, Any, Dict, List, Callable, TypeVar, cast, Type, get_type_hints

import discord
from discord.ext import commands

from utils.command_imports import get_slash_command_class, get_option_class, is_compatible_with_pycord_261
from utils.interaction_handlers import safely_respond_to_interaction, defer_interaction

logger = logging.getLogger(__name__)

# Type definitions for better type checking
CommandT = TypeVar('CommandT', bound=Callable)

class EnhancedSlashCommand(get_slash_command_class()):
    """
    Enhanced SlashCommand class that properly handles parameter parsing
    for py-cord 2.6.1 compatibility.
    
    This subclass overrides the _parse_options method to handle both
    list and dict-like objects properly.
    """
    
    def _parse_options(self, options):
        """
        Enhanced option parser that handles both list and dict-like options.
        
        This is a key fix for py-cord 2.6.1 compatibility, ensuring that
        options are properly extracted regardless of format.
        
        Args:
            options: Options object from the interaction (list or dict-like)
            
        Returns:
            Dict mapping option names to their values
        """
        kwargs = {}
        
        # Handle different option formats
        if isinstance(options, dict):
            # Some versions pass options as a dict already
            return options
        elif hasattr(options, "__iter__") and not isinstance(options, str):
            # List-like object of option objects
            for opt in options:
                name = getattr(opt, "name", None)
                value = getattr(opt, "value", None)
                
                if name is not None:
                    kwargs[name] = value
        elif hasattr(options, "__dict__"):
            # Object with attributes
            for name, value in options.__dict__.items():
                if not name.startswith("_"):
                    kwargs[name] = value
                    
        # If we couldn't parse options, log a warning
        if not kwargs and options:
            logger.warning(f"Failed to parse options: {options}")
            
        return kwargs
        
    async def _invoke_with_parsed_options(self, ctx, kwargs):
        """
        Invoke the callback with properly parsed options.
        
        This method ensures the callback receives correct parameters
        regardless of the py-cord version.
        
        Args:
            ctx: The interaction context
            kwargs: The parsed options dictionary
            
        Returns:
            The result of the callback
        """
        # Get the expected parameter names
        param_names = inspect.signature(self.callback).parameters.keys()
        
        # Filter kwargs to only include expected parameters
        filtered_kwargs = {k: v for k, v in kwargs.items() if k in param_names}
        
        # Invoke the callback with the context and filtered kwargs
        return await self.callback(ctx, **filtered_kwargs)

    async def __call__(self, ctx):
        """
        Properly handle parameter parsing for different py-cord versions.
        
        Args:
            ctx: The interaction context
            
        Returns:
            The result of invoking the callback
        """
        # Get options from the interaction based on py-cord version
        options = getattr(ctx.interaction, "data", {}).get("options", [])
        
        # Parse options into kwargs
        kwargs = self._parse_options(options)
        
        # Invoke the callback with parsed options
        return await self._invoke_with_parsed_options(ctx, kwargs)

def enhanced_slash_command(*args, **kwargs):
    """
    Enhanced slash command decorator that uses the EnhancedSlashCommand class.
    
    This decorator ensures proper parameter handling for py-cord 2.6.1 compatibility.
    
    Args:
        *args: Positional arguments for the slash command
        **kwargs: Keyword arguments for the slash command
        
    Returns:
        A properly configured slash command decorator
    """
    from utils.command_imports import is_compatible_with_pycord_261, HAS_APP_COMMANDS
    
    def decorator(func):
        # Check which command system to use
        if hasattr(commands, "slash_command"):
            # Use native slash_command if available (unlikely for py-cord 2.6.1)
            logger.info("Using commands.slash_command for decoration")
            return commands.slash_command(*args, **kwargs)(func)
        elif HAS_APP_COMMANDS and hasattr(discord.app_commands, "command"):
            # Use app_commands for discord.py
            logger.info("Using discord.app_commands.command for decoration")
            return discord.app_commands.command(*args, **kwargs)(func)
        else:
            # Custom implementation for direct compatibility
            logger.info("Using custom slash command implementation")
            cmd = EnhancedSlashCommand(func, **kwargs)
            
            # Store the command on the function for reference
            func.__slash_command__ = cmd
            return func
    
    return decorator

def option(name, description, **kwargs):
    """
    Enhanced option decorator that works with py-cord 2.6.1.
    
    This is a wrapper around discord.Option that ensures compatibility.
    
    Args:
        name: The name of the option
        description: The description of the option
        **kwargs: Additional option parameters
    
    Returns:
        A properly configured option decorator
    """
    from utils.command_imports import is_compatible_with_pycord_261, HAS_APP_COMMANDS
    
    # Check which command system to use
    if is_compatible_with_pycord_261():
        # For py-cord 2.6.1, we need to create a compatible option object
        # Check if discord.Option exists
        if hasattr(discord, 'Option'):
            return discord.Option(name=name, description=description, **kwargs)
    elif HAS_APP_COMMANDS:
        # For discord.py, we'd use app_commands.Option
        try:
            return discord.app_commands.Option(name=name, description=description, **kwargs)
        except (AttributeError, ImportError):
            pass
    
    # Fallback to getting the class from our compatibility layer
    option_class = get_option_class()
    try:
        return option_class(name=name, description=description, **kwargs)
    except TypeError:
        # Last resort - create a basic parameter description
        logger.warning(f"Could not create option with class {option_class.__name__}, using basic parameter")
        return inspect.Parameter(
            name=name,
            kind=inspect.Parameter.KEYWORD_ONLY,
            annotation=kwargs.get('type', str),
            default=kwargs.get('default', inspect.Parameter.empty)
        )

def command_handler(
    admin_only: bool = False,
    server_owner_only: bool = False,
    guild_only: bool = True,
    cooldown_seconds: Optional[int] = None,
    error_handler: Optional[Callable] = None,
    with_app_command: bool = True
):
    """
    Decorator for command handlers that ensures consistent error handling and permissions.
    
    Args:
        admin_only: If True, only users with admin permissions can use the command
        server_owner_only: If True, only the server owner can use the command
        guild_only: If True, the command can only be used in a guild
        cooldown_seconds: Optional cooldown in seconds
        error_handler: Optional custom error handler
        with_app_command: Whether this decorator is being used with an app_command
        
    Returns:
        Command decorator function
    """
    def decorator(func: CommandT) -> CommandT:
        @functools.wraps(func)
        async def wrapper(self, interaction_or_ctx, *args, **kwargs):
            # Determine if we're working with an interaction or context
            is_interaction = isinstance(interaction_or_ctx, discord.Interaction)
            interaction = interaction_or_ctx if is_interaction else getattr(interaction_or_ctx, "interaction", None)
            ctx = None if is_interaction else interaction_or_ctx
            
            # Setup error handling
            async def send_error(message):
                if is_interaction:
                    await safely_respond_to_interaction(
                        interaction, 
                        content=message,
                        ephemeral=True
                    )
                else:
                    await ctx.reply(message)
                    
            try:
                # Check if command should only be used in a guild
                if guild_only:
                    guild = getattr(interaction, "guild", None) if is_interaction else getattr(ctx, "guild", None)
                    if not guild:
                        await send_error("This command can only be used in a server.")
                        return None
                
                # Check admin permissions if required
                if admin_only:
                    user = getattr(interaction, "user", None) if is_interaction else getattr(ctx, "author", None)
                    permissions = getattr(user, "guild_permissions", None)
                    is_admin = getattr(permissions, "administrator", False) if permissions else False
                    
                    if not is_admin:
                        await send_error("You need administrator permissions to use this command.")
                        return None
                
                # Check server owner if required
                if server_owner_only:
                    user = getattr(interaction, "user", None) if is_interaction else getattr(ctx, "author", None)
                    guild = getattr(interaction, "guild", None) if is_interaction else getattr(ctx, "guild", None)
                    is_owner = user.id == guild.owner_id if user and guild else False
                    
                    if not is_owner:
                        await send_error("Only the server owner can use this command.")
                        return None
                        
                # Apply cooldown if specified
                if cooldown_seconds is not None:
                    # Get user ID for cooldown tracking
                    user_id = getattr(interaction.user, "id", None) if is_interaction else getattr(ctx.author, "id", None)
                    cooldown_key = f"{func.__name__}_{user_id}"
                    
                    # Check if command is on cooldown
                    cooldown = getattr(self, "_command_cooldowns", {}).get(cooldown_key)
                    if cooldown and (discord.utils.utcnow() - cooldown).total_seconds() < cooldown_seconds:
                        remaining = int(cooldown_seconds - (discord.utils.utcnow() - cooldown).total_seconds())
                        await send_error(f"Command on cooldown. Try again in {remaining} seconds.")
                        return None
                    
                    # Initialize cooldown tracking if needed
                    if not hasattr(self, "_command_cooldowns"):
                        self._command_cooldowns = {}
                    
                    # Update cooldown
                    self._command_cooldowns[cooldown_key] = discord.utils.utcnow()
                
                # Execute the command
                return await func(self, interaction_or_ctx, *args, **kwargs)
                
            except Exception as e:
                # Use custom error handler if provided
                if error_handler:
                    return await error_handler(self, interaction_or_ctx, e)
                
                # Default error handling
                logger.exception(f"Error in command {func.__name__}: {e}")
                try:
                    await send_error(f"An error occurred: {str(e)}")
                except Exception as e2:
                    logger.error(f"Failed to send error message: {e2}")
                
                return None
                
        return wrapper
    return decorator

def db_operation(
    collection_name: Optional[str] = None,
    error_message: str = "Database operation failed",
    require_success: bool = True
):
    """
    Decorator for database operations with error handling.
    
    Args:
        collection_name: Name of the collection to operate on, or None to pass the db directly
        error_message: Custom error message to display on failure
        require_success: Whether the operation must succeed for the command to continue
        
    Returns:
        Database operation decorator function
    """
    def decorator(func: CommandT) -> CommandT:
        @functools.wraps(func)
        async def wrapper(self, *args, **kwargs):
            try:
                # Get database connection
                db = getattr(self.bot, "db", None)
                if not db:
                    logger.error("Database connection not available")
                    return {"success": False, "error": "Database connection not available"}
                
                # Pass the collection or db to the function
                if collection_name:
                    collection = getattr(db, collection_name, None)
                    if not collection:
                        logger.error(f"Collection {collection_name} not found")
                        return {"success": False, "error": f"Collection {collection_name} not found"}
                    result = await func(self, collection, *args, **kwargs)
                else:
                    result = await func(self, db, *args, **kwargs)
                
                return result
            except Exception as e:
                # Log the error
                logger.exception(f"Database operation error in {func.__name__}: {e}")
                
                # Return error result
                if require_success:
                    raise
                return {"success": False, "error": f"{error_message}: {str(e)}"}
        
        return wrapper
    return decorator