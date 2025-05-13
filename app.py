"""
Minimal entry point for Replit to start the Discord bot

This file is just a shim to satisfy Replit's expectations
while launching the actual Discord bot process without Flask.
"""

import os
import sys
import subprocess
import time
import signal
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger("app")

# Discord bot process
bot_process = None

def start_discord_bot():
    """
    Start the Discord bot in a subprocess
    """
    global bot_process
    
    try:
        logger.info("Starting Discord bot from app.py shim...")
        # Run our launcher script
        bot_process = subprocess.Popen(
            ["bash", "launcher.sh"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            preexec_fn=os.setsid
        )
        
        # Log output from bot process
        for line in bot_process.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
        
        # Wait for process to complete
        bot_process.wait()
        
        if bot_process.returncode != 0:
            logger.error(f"Discord bot process exited with code {bot_process.returncode}")
        else:
            logger.info("Discord bot process exited successfully")
            
    except Exception as e:
        logger.error(f"Failed to start Discord bot process: {e}")
        import traceback
        logger.error(traceback.format_exc())

def cleanup(signum, frame):
    """
    Cleanup function to terminate the bot process when this script is stopped
    """
    global bot_process
    
    if bot_process:
        logger.info("Terminating Discord bot process...")
        try:
            os.killpg(os.getpgid(bot_process.pid), signal.SIGTERM)
            bot_process.wait(timeout=5)
            logger.info("Discord bot process terminated")
        except Exception as e:
            logger.error(f"Failed to terminate Discord bot process: {e}")
    
    # Exit this process
    sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGINT, cleanup)
signal.signal(signal.SIGTERM, cleanup)

# Main entry point - Just start the Discord bot
if __name__ == "__main__":
    # This is a simple message to show in Replit's console
    print("=" * 60)
    print("  TOWER OF TEMPTATION DISCORD BOT (Replit Entry Point)")
    print("  Starting Discord bot without web server components")
    print("  " + time.strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 60)
    
    # Start the Discord bot
    start_discord_bot()
    
    # Keep this process alive
    try:
        while True:
            time.sleep(10)
    except KeyboardInterrupt:
        cleanup(None, None)