#!/bin/bash
# Entry point script for Discord bot
# This script is used by the Replit workflow system

# Set environment path
export PYTHONPATH="."
export PYTHONUNBUFFERED="1"

# Print banner
echo "====================================================="
echo "  Discord Bot Starting"
echo "  $(date)"
echo "====================================================="

# Run the bot
python main_entry.py