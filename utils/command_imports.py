"""
Command Import and Registration Utilities

This module provides utilities for safely importing and registering
commands with py-cord 2.6.1 and ensuring compatibility with the Discord API.
"""

import logging
import inspect
import discord
from typing import Any, Dict, List, Optional, Union, Callable, Type, TypeVar, cast

logger = logging.getLogger(__name__)

# Check the py-cord version
try:
    from discord import __version__ as discord_version
    PYCORD_VERSION = discord_version
    logger.info(f"Using py-cord version: {PYCORD_VERSION}")
except (ImportError, AttributeError):
    PYCORD_VERSION = "unknown"
    logger.warning("Unable to determine py-cord version")

T = TypeVar('T')

def get_slash_command_class() -> Type:
    """
    Get the appropriate SlashCommand class based on the detected py-cord version.
    
    Returns:
        The SlashCommand class
    """
    # Always use the SlashCommand from the current py-cord version
    if hasattr(discord, 'SlashCommand'):
        return getattr(discord, 'SlashCommand')
    
    # Fallback approach if the class name changed
    try:
        # Check if it's available under a different name or location
        app_command_module = getattr(discord, 'application_command', None)
        if app_command_module and hasattr(app_command_module, 'SlashCommand'):
            return getattr(app_command_module, 'SlashCommand')
        
        slash_module = getattr(discord, 'slash_command', None)
        if slash_module and hasattr(slash_module, 'SlashCommand'):
            return getattr(slash_module, 'SlashCommand')
        
        # Last resort, try importing directly
        from discord.commands import SlashCommand
        return SlashCommand
    except ImportError:
        logger.error("Failed to import SlashCommand - using a placeholder")
        # Create a placeholder class if we can't find the real one
        class PlaceholderSlashCommand:
            pass
        return PlaceholderSlashCommand

def get_option_class() -> Type:
    """
    Get the appropriate Option class based on the detected py-cord version.
    
    Returns:
        The Option class
    """
    # Direct approach
    if hasattr(discord, 'Option'):
        return getattr(discord, 'Option')
    
    # Fallback approaches
    try:
        # Try different possible locations
        option_module = getattr(discord, 'option', None)
        if option_module and hasattr(option_module, 'Option'):
            return getattr(option_module, 'Option')
        
        commands_module = getattr(discord, 'commands', None)
        if commands_module and hasattr(commands_module, 'Option'):
            return getattr(commands_module, 'Option')
        
        # Last resort, try importing directly
        from discord.commands import Option
        return Option
    except ImportError:
        logger.error("Failed to import Option - using a placeholder")
        # Create a placeholder class if we can't find the real one
        class PlaceholderOption:
            pass
        return PlaceholderOption

def safely_get_command_parameter_names(command_func: Callable) -> List[str]:
    """
    Safely extract parameter names from a command function with error handling.
    
    Args:
        command_func: The command function to inspect
        
    Returns:
        List of parameter names (excluding 'self' and 'ctx')
    """
    try:
        # Use inspect to get the signature
        signature = inspect.signature(command_func)
        
        # Filter out self and context parameters
        param_names = [
            name for name, param in signature.parameters.items()
            if name not in ('self', 'ctx', 'context', 'interaction')
        ]
        
        return param_names
    except (ValueError, TypeError) as e:
        logger.error(f"Failed to get command parameters: {e}")
        return []

def safely_copy_metadata(source: Callable, target: Callable) -> None:
    """
    Safely copy function metadata from source to target.
    
    Args:
        source: Source function to copy metadata from
        target: Target function to copy metadata to
    """
    try:
        # Use functools.update_wrapper instead of direct attribute copies
        import functools
        functools.update_wrapper(target, source)
    except Exception as e:
        logger.error(f"Failed to copy function metadata: {e}")
        
        # Fallback: copy only the most important attributes
        for attr in ['__name__', '__doc__', '__module__']:
            try:
                if hasattr(source, attr):
                    setattr(target, attr, getattr(source, attr))
            except Exception:
                pass

def is_compatible_with_pycord_261() -> bool:
    """
    Check if we're running a version of py-cord that's compatible with 2.6.1.
    
    Returns:
        bool: True if running a compatible version, False otherwise
    """
    try:
        # Parse version parts
        version_parts = PYCORD_VERSION.split('.')
        
        # We need at least 3 parts (major.minor.patch)
        if len(version_parts) < 3:
            return False
        
        # Extract major, minor, patch
        major = int(version_parts[0])
        minor = int(version_parts[1])
        patch = int(version_parts[2])
        
        # Check if we're on 2.6.1 or newer
        return (major > 2 or 
                (major == 2 and minor > 6) or
                (major == 2 and minor == 6 and patch >= 1))
    except (ValueError, IndexError):
        # If we can't parse the version, assume incompatible
        return False