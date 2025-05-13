"""
Command Imports for Discord API Compatibility

This module provides compatibility layers for importing functionality
from py-cord, handling different versions gracefully to ensure code
can work consistently across library versions.
"""

import logging
import inspect
from typing import Any, Dict, List, Optional, Union, Callable, Tuple, Type, get_type_hints
import sys
import importlib.metadata

# Set up logger
logger = logging.getLogger(__name__)

# Try to determine if we're using py-cord through package metadata
try:
    pycord_version = importlib.metadata.version('py-cord')
    logger.info(f"Detected py-cord version from metadata: {pycord_version}")
    IS_PYCORD = True
    PYCORD_261 = pycord_version.startswith("2.6.1")
except (importlib.metadata.PackageNotFoundError, Exception) as e:
    logger.warning(f"py-cord not found in package metadata: {e}")
    IS_PYCORD = False
    PYCORD_261 = False

# Attempt imports with proper error handling
try:
    import discord
    from discord.ext import commands
    
    # Report Discord version
    if hasattr(discord, '__version__'):
        logger.info(f"Detected discord.__version__: {discord.__version__}")
        # Use version string to detect py-cord if metadata didn't work
        if not IS_PYCORD:
            # These are py-cord version patterns
            IS_PYCORD = discord.__version__ in ["2.5.2", "2.6.1"]
    
    # Determine if we're using discord.py or py-cord
    HAS_APP_COMMANDS = hasattr(discord, 'app_commands')
    HAS_COMMANDS = hasattr(discord, 'commands')
    
    logger.info(f"Using py-cord: {IS_PYCORD}")
    logger.info(f"Has discord.app_commands: {HAS_APP_COMMANDS}")
    logger.info(f"Has discord.commands: {HAS_COMMANDS}")
    
    # Attempt to import proper classes based on what's available
    if HAS_APP_COMMANDS:
        # This is discord.py style
        try:
            from discord.app_commands import Command as SlashCommand
            from discord.app_commands import Option
            PYCORD_IMPORTS = False
            logger.info("Using discord.app_commands for SlashCommand and Option")
        except ImportError as e:
            logger.error(f"Error importing from discord.app_commands: {e}")
            SlashCommand = commands.Command
            Option = object
            PYCORD_IMPORTS = False
    else:
        # Default to traditional commands
        SlashCommand = commands.Command
        Option = object
        PYCORD_IMPORTS = False
        logger.info("Using traditional commands.Command")
    
    # Special handling for slash_command in commands
    commands.has_slash_command = hasattr(commands, "slash_command")
    
except ImportError as e:
    logger.error(f"Error importing Discord libraries: {e}")
    # Define placeholders for type checking
    class SlashCommand:
        pass
    
    class Option:
        pass
    
    IS_PYCORD = False
    PYCORD_IMPORTS = False
    PYCORD_261 = False

# Additional compatibility flags
HAS_RESPOND_METHOD = False
HAS_RESPONSE_PROPERTY = False

# Check Interaction properties if available
try:
    if hasattr(discord, 'Interaction'):
        HAS_RESPOND_METHOD = hasattr(discord.Interaction, 'respond')
        HAS_RESPONSE_PROPERTY = hasattr(discord.Interaction, 'response')
        logger.info(f"Interaction.respond: {HAS_RESPOND_METHOD}")
        logger.info(f"Interaction.response: {HAS_RESPONSE_PROPERTY}")
except Exception as e:
    logger.error(f"Error checking Interaction properties: {e}")

def get_slash_command_class() -> Type:
    """
    Get the appropriate SlashCommand class for this environment.
    
    Returns:
        The SlashCommand class to use
    """
    # Return the appropriate class based on environment
    if IS_PYCORD and PYCORD_261:
        # For py-cord 2.6.1, we need specific handling
        logger.info("Using SlashCommand appropriate for py-cord 2.6.1")
        return SlashCommand
    elif HAS_APP_COMMANDS:
        # For discord.py or compatible libraries
        logger.info("Using app_commands.Command")
        try:
            from discord.app_commands import Command
            return Command
        except ImportError:
            return SlashCommand
    else:
        # Fallback to what we imported earlier
        return SlashCommand

def get_option_class() -> Type:
    """
    Get the appropriate Option class for this environment.
    
    Returns:
        The Option class to use
    """
    # Return the appropriate class based on environment
    if IS_PYCORD and PYCORD_261:
        # For py-cord 2.6.1, we need specific handling
        return Option
    elif HAS_APP_COMMANDS:
        # For discord.py or compatible libraries
        try:
            from discord.app_commands import Option as AppOption
            return AppOption
        except ImportError:
            return Option
    else:
        # Fallback to what we imported earlier
        return Option

def is_compatible_with_pycord_261() -> bool:
    """
    Check if the current environment is compatible with py-cord 2.6.1.
    
    Returns:
        True if compatible, False otherwise
    """
    compatibility = PYCORD_261 or (
        IS_PYCORD and 
        hasattr(discord, '__version__') and 
        (discord.__version__ == '2.5.2' or discord.__version__ == '2.6.1')
    )
    
    logger.info(f"py-cord 2.6.1 compatibility: {compatibility}")
    return compatibility

def safely_copy_metadata(src_func: Callable, dest_func: Callable) -> None:
    """
    Safely copy function metadata between functions.
    
    Args:
        src_func: Source function
        dest_func: Destination function
    """
    for attr in ['__name__', '__doc__', '__module__', '__annotations__', '__qualname__']:
        try:
            if hasattr(src_func, attr):
                setattr(dest_func, attr, getattr(src_func, attr))
        except (AttributeError, TypeError):
            pass

def safely_get_command_parameter_names(func: Callable) -> List[str]:
    """
    Safely get parameter names from a function.
    
    This handles different function types and ensures consistent results.
    
    Args:
        func: The function to inspect
        
    Returns:
        List of parameter names
    """
    try:
        # Try to use inspect signature first (most reliable)
        sig = inspect.signature(func)
        # Skip self/cls for methods
        params = list(sig.parameters.keys())
        if params and params[0] in ('self', 'cls'):
            params = params[1:]
        return params
    except (ValueError, TypeError):
        # Fallback for built-ins or other special cases
        try:
            # Try to use get_type_hints for type annotations
            type_hints = get_type_hints(func)
            # Remove return annotation if present
            if 'return' in type_hints:
                del type_hints['return']
            return list(type_hints.keys())
        except (TypeError, ValueError, KeyError):
            # Last resort, look at func.__code__ if available
            if hasattr(func, '__code__'):
                co_varnames = func.__code__.co_varnames
                arg_count = func.__code__.co_argcount
                params = list(co_varnames[:arg_count])
                # Skip self/cls for methods
                if params and params[0] in ('self', 'cls'):
                    params = params[1:]
                return params
            
            # If everything fails, return empty list
            return []