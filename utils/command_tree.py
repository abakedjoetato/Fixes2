"""
Command Tree Utilities

This module provides functions for creating and managing command trees
with compatibility across different versions of py-cord and discord.py.
"""

import logging
import inspect
from typing import Optional, List, Any, Dict, Type, Callable, Union

import discord
from discord.ext import commands

from utils.command_imports import (
    is_compatible_with_pycord_261, 
    HAS_APP_COMMANDS,
    PYCORD_261,
    IS_PYCORD
)

logger = logging.getLogger(__name__)

def create_command_tree(bot: commands.Bot):
    """
    Create a command tree that's compatible with the current version
    of discord.py or py-cord.
    
    Args:
        bot: The Discord bot instance
        
    Returns:
        A command tree or similar object for registering commands
    """
    try:
        # Check which library we're using
        if is_compatible_with_pycord_261():
            # py-cord 2.6.1 - CommandTree is embedded in the bot already
            logger.info("Using py-cord 2.6.1 native command handling")
            # Return the bot itself as it has the command registration methods
            return bot
        elif HAS_APP_COMMANDS:
            # discord.py style with CommandTree
            logger.info("Using discord.py CommandTree")
            return discord.app_commands.CommandTree(bot)
        else:
            # Legacy approach - the bot itself handles commands
            logger.info("Using legacy command handling")
            return bot
    except Exception as e:
        logger.error(f"Error creating command tree: {e}")
        # Return a minimal object to avoid errors
        return None

def register_command(
    command_tree: Any,
    command: Callable,
    name: Optional[str] = None,
    description: Optional[str] = None,
    guild_ids: Optional[List[int]] = None
):
    """
    Register a command with the appropriate command tree
    
    Args:
        command_tree: The command tree to register with
        command: The command function/object to register
        name: Optional name for the command
        description: Optional description for the command
        guild_ids: Optional list of guild IDs to register with
        
    Returns:
        The registered command
    """
    try:
        # Determine command name if not provided
        if not name:
            name = getattr(command, "name", command.__name__)
            
        # Determine if it's a function or Command object
        is_function = inspect.isfunction(command)
        
        if is_compatible_with_pycord_261():
            # py-cord 2.6.1 approach
            if hasattr(command_tree, "add_application_command"):
                logger.info(f"Registering command {name} with py-cord 2.6.1")
                # Command is already a Command object
                if not is_function:
                    command_tree.add_application_command(command)
                    return command
                
                # Convert function to Command as needed
                # This is a simplified version
                from utils.command_handlers import enhanced_slash_command
                cmd = enhanced_slash_command(
                    name=name, 
                    description=description or "No description provided"
                )(command)
                return cmd
        elif HAS_APP_COMMANDS:
            # discord.py style
            logger.info(f"Registering command {name} with discord.py CommandTree")
            if guild_ids:
                # Register as guild command
                for guild_id in guild_ids:
                    command_tree.command(
                        name=name,
                        description=description,
                        guild=discord.Object(id=guild_id)
                    )(command)
            else:
                # Register as global command
                command_tree.command(
                    name=name,
                    description=description
                )(command)
            return command
        else:
            # Legacy approach
            logger.info(f"Using legacy command registration for {name}")
            if hasattr(command_tree, "add_command"):
                command_tree.add_command(command)
            return command
    except Exception as e:
        logger.error(f"Error registering command {name}: {e}")
        return command

async def sync_command_tree(
    bot: commands.Bot,
    command_tree: Any,
    guild_ids: Optional[List[int]] = None,
    sync_global: bool = True
):
    """
    Sync the command tree with Discord
    
    Args:
        bot: The Discord bot instance
        command_tree: The command tree to sync
        guild_ids: Optional list of guild IDs to sync with
        sync_global: Whether to sync global commands
        
    Returns:
        Success status
    """
    try:
        # Determine the sync method
        if is_compatible_with_pycord_261():
            # py-cord 2.6.1 uses different sync method
            logger.info("Syncing commands with py-cord 2.6.1")
            if hasattr(bot, "sync_commands"):
                # Use the bot's sync_commands method
                await bot.sync_commands(
                    register_guild_commands=bool(guild_ids),
                    guild_ids=guild_ids,
                    delete_existing=True
                )
                return True
            return False
        elif HAS_APP_COMMANDS:
            # discord.py style
            logger.info("Syncing commands with discord.py CommandTree")
            if guild_ids:
                # Sync to specific guilds
                for guild_id in guild_ids:
                    await command_tree.sync(guild=discord.Object(id=guild_id))
            
            if sync_global:
                # Sync global commands
                await command_tree.sync()
            return True
        else:
            # Legacy approach
            logger.info("Using legacy command sync")
            return True
    except Exception as e:
        logger.error(f"Error syncing command tree: {e}")
        return False