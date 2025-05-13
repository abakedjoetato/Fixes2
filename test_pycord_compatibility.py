"""
Test script to verify py-cord 2.6.1 compatibility of the interaction handlers.

This script checks if our compatibility layers properly work with py-cord 2.6.1.
"""

import asyncio
import logging
import sys
import os
import traceback
import importlib.metadata

# Setup logging first
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Main test function to collect compatibility information
def run_compatibility_test():
    """Run the compatibility test and report findings"""
    
    logger.info("==== py-cord 2.6.1 Compatibility Test ====")

    # Check installed versions through package metadata
    try:
        pycord_version = importlib.metadata.version('py-cord')
        logger.info(f"Installed py-cord version from metadata: {pycord_version}")
    except importlib.metadata.PackageNotFoundError:
        logger.warning("py-cord package not found through metadata")
        pycord_version = None
        
    # Try importing discord and check its version
    try:
        import discord
        if hasattr(discord, '__version__'):
            logger.info(f"discord.__version__: {discord.__version__}")
        else:
            logger.warning("Discord library has no __version__ attribute")
            
        logger.info(f"Discord package location: {discord.__file__}")
        
        # Check Interaction class attributes for compatibility
        interactions_module = getattr(discord, 'interactions', None)
        interaction_class = getattr(discord, 'Interaction', None)
        
        if interaction_class:
            logger.info(f"Interaction class found at: {interaction_class.__module__}")
            logger.info(f"Interaction class dir: {dir(interaction_class)}")
            
            # Check for key methods
            has_respond = hasattr(interaction_class, "respond")
            has_response = hasattr(interaction_class, "response")
            logger.info(f"Interaction.respond: {has_respond}")
            logger.info(f"Interaction.response: {has_response}")
        else:
            logger.warning("Could not find Interaction class")
            
        # Check commands structure
        from discord.ext import commands
        logger.info(f"Commands module location: {commands.__file__}")
        
        has_slash_command = hasattr(commands, "slash_command")
        logger.info(f"commands.slash_command: {has_slash_command}")
        
        has_app_commands = hasattr(discord, "app_commands")
        logger.info(f"discord.app_commands: {has_app_commands}")
        
        # Check for specific py-cord modules
        has_commands_dir = hasattr(discord, "commands")
        logger.info(f"discord.commands directory: {has_commands_dir}")
        
        if has_commands_dir:
            try:
                # For py-cord 2.x, check for SlashCommand in commands
                import discord.commands
                logger.info(f"discord.commands dir: {dir(discord.commands)}")
                has_slash_command_class = hasattr(discord.commands, "SlashCommand")
                logger.info(f"discord.commands.SlashCommand: {has_slash_command_class}")
            except ImportError as e:
                logger.error(f"Error importing discord.commands: {e}")
    
    except ImportError as e:
        logger.error(f"Error importing discord: {e}")
        traceback.print_exc()
        return

    logger.info("\n==== Testing Our Compatibility Modules ====")
    
    # Test our compatibility modules
    try:
        logger.info("Testing utils.interaction_handlers...")
        import utils.interaction_handlers
        logger.info(f"HAS_RESPOND_METHOD: {utils.interaction_handlers.HAS_RESPOND_METHOD}")
        logger.info(f"HAS_RESPONSE_PROPERTY: {utils.interaction_handlers.HAS_RESPONSE_PROPERTY}")
    except ImportError as e:
        logger.error(f"Error importing utils.interaction_handlers: {e}")
        traceback.print_exc()
        
    try:
        logger.info("\nTesting utils.command_imports...")
        import utils.command_imports
        logger.info(f"PYCORD_IMPORTS: {utils.command_imports.PYCORD_IMPORTS}")
        logger.info(f"PYCORD_261: {utils.command_imports.PYCORD_261}")
        
        slash_command_class = utils.command_imports.get_slash_command_class()
        option_class = utils.command_imports.get_option_class()
        logger.info(f"get_slash_command_class(): {slash_command_class.__name__}")
        logger.info(f"get_option_class(): {option_class.__name__}")
    except ImportError as e:
        logger.error(f"Error importing utils.command_imports: {e}")
        traceback.print_exc()
        
    logger.info("==== Compatibility Test Complete ====")

# Main execution
if __name__ == "__main__":
    try:
        run_compatibility_test()
    except Exception as e:
        logger.error(f"Fatal error during compatibility test: {e}")
        traceback.print_exc()