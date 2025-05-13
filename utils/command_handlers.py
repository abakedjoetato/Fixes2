"""
Enhanced Command Handlers for Discord API

This module implements proper subclassing of the SlashCommand class
to fix incompatibilities with py-cord 2.6.1, particularly in the
parameter handling for slash commands.
"""

import logging
import inspect
from typing import Any, Dict, List, Optional, Union, Callable, Tuple, ClassVar
import functools

import discord
from discord.ext import commands

from utils.command_imports import (
    get_slash_command_class,
    get_option_class,
    safely_get_command_parameter_names,
    safely_copy_metadata,
    is_compatible_with_pycord_261
)

logger = logging.getLogger(__name__)

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
        result = {}
        
        # Handle list-style options (py-cord 2.6.1+)
        if isinstance(options, list):
            for option in options:
                # Extract name and value using attribute access if possible
                if hasattr(option, 'name') and hasattr(option, 'value'):
                    result[option.name] = option.value
                # Fallback to dictionary access if needed
                elif isinstance(option, dict) and 'name' in option and 'value' in option:
                    result[option['name']] = option['value']
        
        # Handle dict-style options (older versions)
        elif hasattr(options, 'items') and callable(options.items):
            try:
                for name, value in options.items():
                    result[name] = value
            except (TypeError, AttributeError) as e:
                # Log the error and try a different approach
                logger.debug(f"Error using items(): {e}")
                
                # Try dictionary-style access as fallback
                if hasattr(options, 'keys') and callable(options.keys):
                    for key in options.keys():
                        try:
                            result[key] = options[key]
                        except Exception:
                            pass
        
        # Handle other types of objects by attempting attribute extraction
        else:
            # Try common attribute names that might contain options
            for key in ['options', 'values', 'parameters']:
                if hasattr(options, key):
                    try:
                        value = getattr(options, key)
                        # Recursively parse if we got another container
                        if isinstance(value, (list, dict)) or hasattr(value, 'items'):
                            sub_results = self._parse_options(value)
                            result.update(sub_results)
                    except Exception:
                        pass
        
        return result
    
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
        if not self.callback:
            return None
        
        try:
            # Get required parameters from the callback signature
            params = safely_get_command_parameter_names(self.callback)
            
            # Filter the kwargs to only include parameters the callback expects
            filtered_kwargs = {k: v for k, v in kwargs.items() if k in params}
            
            # Call the callback with the context and filtered kwargs
            return await self.callback(ctx, **filtered_kwargs)
        except Exception as e:
            logger.error(f"Error invoking command callback: {e}")
            # Re-raise to let the global error handler deal with it
            raise

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
    def decorator(func):
        # Check if we can subclass the SlashCommand properly
        if is_compatible_with_pycord_261():
            # Create an instance of our enhanced slash command
            cmd = EnhancedSlashCommand(func, *args, **kwargs)
            return cmd
        else:
            # Fall back to the standard slash command if compatibility is an issue
            logger.warning("Using standard SlashCommand as fallback")
            SlashCommand = get_slash_command_class()
            return SlashCommand(func, *args, **kwargs)
    
    return decorator

# Helper function for adding options to commands
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
    Option = get_option_class()
    return Option(name=name, description=description, **kwargs)