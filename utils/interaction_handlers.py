"""
Enhanced interaction handlers for py-cord compatibility

This module provides compatibility layers for interacting with Discord's
interaction system across different versions of py-cord and discord.py.
It specifically addresses the issue where Interaction.respond is not available
in py-cord 2.6.1.
"""

import logging
import inspect
import asyncio
from typing import Optional, Union, Any, Dict, Callable, List, TypeVar, cast

import discord
from discord.ext import commands

logger = logging.getLogger(__name__)

# Py-cord compatibility constants
HAS_RESPOND_METHOD = hasattr(discord.Interaction, "respond")
HAS_RESPONSE_PROPERTY = hasattr(discord.Interaction, "response")

# Type definitions for better type checking
InteractionResponseType = Optional[Union[discord.Message, discord.WebhookMessage]]
EmbedType = Optional[discord.Embed]
EmbedsType = Optional[List[discord.Embed]]
FileType = Optional[discord.File]
FilesType = Optional[List[discord.File]]
ViewType = Optional[discord.ui.View]
AllowedMentionsType = Optional[discord.AllowedMentions]

async def safely_respond_to_interaction(
    interaction: discord.Interaction,
    content: Optional[str] = None,
    *,
    embed: EmbedType = None,
    embeds: EmbedsType = None,
    ephemeral: bool = False,
    view: ViewType = None,
    tts: bool = False,
    file: FileType = None,
    files: FilesType = None,
    allowed_mentions: AllowedMentionsType = None,
    delete_after: Optional[float] = None,
    wait: bool = False
) -> InteractionResponseType:
    """
    Safely respond to an interaction with py-cord compatibility
    
    This function handles the differences between py-cord and discord.py
    for responding to interactions.
    
    Args:
        interaction: The Discord interaction to respond to
        content: Text content of the response
        embed: A single embed to include
        embeds: List of embeds to include (overrides embed)
        ephemeral: Whether the message should be ephemeral
        view: View components to include
        tts: Text-to-speech flag
        file: Single file attachment
        files: List of file attachments
        allowed_mentions: Allowed mentions config
        delete_after: Time in seconds to delete after
        wait: Whether to wait for the message
        
    Returns:
        Optional message object if successful
    """
    try:
        # Special case for embeds - if we have a single embed, ensure it's properly set
        if embed is not None and embeds is None:
            embeds = [embed]
        
        # Determine what response mechanism is available
        if interaction.response.is_done():
            # Already responded or deferred, use followup
            try:
                # py-cord followup (most common case)
                kwargs = {
                    "content": content,
                    "embeds": embeds,
                    "ephemeral": ephemeral,
                    "view": view,
                    "tts": tts,
                    "allowed_mentions": allowed_mentions,
                }
                
                # Add optional parameters only if they're provided
                if file is not None:
                    kwargs["file"] = file
                if files is not None:
                    kwargs["files"] = files
                if wait:
                    kwargs["wait"] = wait
                    
                return await interaction.followup.send(**kwargs)
            except (AttributeError, TypeError) as e:
                # Discord.py fallback or channel is None
                logger.warning(f"Followup send failed, trying channel: {e}")
                if interaction.channel:
                    kwargs = {
                        "content": content,
                        "embeds": embeds,
                        "view": view,
                        "tts": tts,
                        "allowed_mentions": allowed_mentions,
                    }
                    
                    # Add optional parameters only if they're provided
                    if file is not None:
                        kwargs["file"] = file
                    if files is not None:
                        kwargs["files"] = files
                    if delete_after is not None:
                        kwargs["delete_after"] = delete_after
                        
                    return await interaction.channel.send(**kwargs)
                else:
                    logger.error("No channel available for response")
                    return None
        else:
            # Not yet responded - this is the py-cord 2.6.1 path
            try:
                kwargs = {
                    "content": content,
                    "embeds": embeds,
                    "ephemeral": ephemeral,
                    "view": view,
                    "tts": tts,
                    "allowed_mentions": allowed_mentions,
                }
                
                # Add optional parameters only if they're provided
                if file is not None:
                    kwargs["file"] = file
                if files is not None:
                    kwargs["files"] = files
                    
                # py-cord 2.x - this is the primary path for py-cord 2.6.1
                return await interaction.response.send_message(**kwargs)
            except (AttributeError, TypeError) as e:
                # Discord.py path (respond) - not expected with py-cord 2.6.1
                logger.warning(f"Response send_message failed, trying respond: {e}")
                if HAS_RESPOND_METHOD:
                    kwargs = {
                        "content": content,
                        "embeds": embeds,
                        "ephemeral": ephemeral,
                        "view": view,
                        "tts": tts,
                        "allowed_mentions": allowed_mentions,
                    }
                    
                    # Add optional parameters
                    if file is not None:
                        kwargs["file"] = file
                    if files is not None:
                        kwargs["files"] = files
                    if delete_after is not None:
                        kwargs["delete_after"] = delete_after
                        
                    # This needs a cast to ignore the typing error since py-cord doesn't have this
                    interaction_with_respond = cast(Any, interaction)
                    return await interaction_with_respond.respond(**kwargs)
                else:
                    # Fallback for older versions
                    logger.error("Could not find a compatible way to respond to the interaction")
                    return None
    except Exception as e:
        logger.error(f"Error responding to interaction: {e}")
        try:
            # Last-resort attempt
            if interaction.channel:
                await interaction.channel.send(content="There was an error processing this command.")
        except Exception:
            pass
        return None

async def defer_interaction(
    interaction: discord.Interaction,
    *,
    ephemeral: bool = False,
    thinking: bool = True
) -> bool:
    """
    Safely defer an interaction with py-cord compatibility
    
    This function handles the differences between py-cord and discord.py
    for deferring interactions.
    
    Args:
        interaction: The Discord interaction to defer
        ephemeral: Whether the response should be ephemeral
        thinking: Whether to show a thinking state
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        if interaction.response.is_done():
            # Already responded or deferred
            return True
        
        # Primary path for py-cord 2.6.1
        try:
            # Specify only the parameters we know are valid for py-cord 2.6.1
            kwargs = {"ephemeral": ephemeral}
            
            # Some versions of py-cord support thinking
            if hasattr(interaction.response, "defer") and "thinking" in inspect.signature(interaction.response.defer).parameters:
                kwargs["thinking"] = thinking
                
            await interaction.response.defer(**kwargs)
            return True
        except (AttributeError, TypeError) as e:
            # Fallback for discord.py or very old py-cord
            logger.warning(f"Response defer failed, trying alternate method: {e}")
            
            if HAS_DEFER_METHOD:
                # This is for discord.py - cast to avoid type errors
                interaction_with_defer = cast(Any, interaction)
                await interaction_with_defer.defer(ephemeral=ephemeral)
                return True
            else:
                # Final fallback - just send a message
                logger.error("Could not find a compatible way to defer the interaction")
                await safely_respond_to_interaction(
                    interaction,
                    content="Processing your request...",
                    ephemeral=ephemeral
                )
                return False
    except Exception as e:
        logger.error(f"Error deferring interaction: {e}")
        try:
            # If all else fails, try to send a message
            if not interaction.response.is_done():
                await safely_respond_to_interaction(
                    interaction,
                    content="Processing your request...",
                    ephemeral=ephemeral
                )
        except Exception:
            pass
        return False

def create_modal(
    title: str,
    custom_id: str,
    inputs: Dict[str, Dict[str, Any]]
) -> discord.ui.Modal:
    """
    Create a modal dialog with compatibility across library versions
    
    Args:
        title: Modal title
        custom_id: Custom ID for the modal
        inputs: Dictionary of inputs where keys are custom_ids and values are configs
        
    Returns:
        Modal object
    """
    try:
        # This check ensures we're using the proper Modal class
        if hasattr(discord.ui, "Modal"):
            # py-cord 2.x - this is the preferred path for py-cord 2.6.1
            modal = discord.ui.Modal(title=title, custom_id=custom_id)
            
            # Determine which input class to use - py-cord 2.6.1 uses TextInput
            input_class = None
            if hasattr(discord.ui, "TextInput"):
                input_class = discord.ui.TextInput
                style_enum = getattr(discord, "TextInputStyle", None)
            elif hasattr(discord.ui, "InputText"):
                input_class = discord.ui.InputText
                style_enum = getattr(discord, "InputTextStyle", None)
            else:
                logger.error("Could not find appropriate input text class")
                raise ValueError("No appropriate input text class found")
            
            # Add each input with appropriate parameters
            for input_id, config in inputs.items():
                # Default style to short (1) if style_enum not found
                default_style = style_enum.short if style_enum else 1
                
                # Create input parameters with only supported attributes
                item_kwargs = {
                    "label": config.get("label", "Input"),
                    "custom_id": input_id,
                    "style": config.get("style", default_style),
                    "required": config.get("required", True),
                }
                
                # Add optional parameters only if they are provided
                placeholder = config.get("placeholder", None)
                if placeholder is not None:
                    item_kwargs["placeholder"] = placeholder
                
                default = config.get("default", None)
                if default is not None:
                    item_kwargs["default"] = default
                
                min_length = config.get("min_length", None)
                if min_length is not None:
                    item_kwargs["min_length"] = min_length
                    
                max_length = config.get("max_length", None)
                if max_length is not None:
                    item_kwargs["max_length"] = max_length
                
                # Create and add the input element
                input_item = input_class(**item_kwargs)
                modal.add_item(input_item)
            
            return modal
        else:
            # Fallback for older versions - although py-cord 2.6.1 should have Modal
            logger.error("Modal creation is not supported in this version")
            raise ValueError("Modal creation not supported")
    except Exception as e:
        logger.error(f"Error creating modal: {e}")
        raise ValueError(f"Modal creation failed: {e}") from e

# Detect if defer method exists directly on Interaction
HAS_DEFER_METHOD = hasattr(discord.Interaction, "defer")