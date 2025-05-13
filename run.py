#!/usr/bin/env python3
"""
Tower of Temptation PvP Statistics Bot - Runner Script

This script runs the Discord bot directly without using any web servers.
It simply imports and runs the main module, which contains the Discord bot logic.
"""

import logging
import sys
import asyncio
from keep_alive import keep_alive

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log")
    ]
)
logger = logging.getLogger("run")

# Start the keep-alive mechanism (non-web-server)
keep_alive()

try:
    logger.info("Starting Discord bot...")
    
    # Import and run the main module
    import main
    
    # If we're running in Python 3.7+, we need to use asyncio.run
    if sys.version_info >= (3, 7):
        try:
            asyncio.run(main.run_bot())
        except KeyboardInterrupt:
            logger.info("Bot stopped by keyboard interrupt")
    else:
        # For older Python versions
        loop = asyncio.get_event_loop()
        try:
            loop.run_until_complete(main.run_bot())
        except KeyboardInterrupt:
            logger.info("Bot stopped by keyboard interrupt")
        finally:
            loop.close()
            
except Exception as e:
    logger.critical(f"Failed to run bot: {e}")
    import traceback
    logger.critical(traceback.format_exc())
    sys.exit(1)