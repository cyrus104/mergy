"""Mergy CLI - Computer Data Organization Tool.

A command-line interface for intelligently merging folders across multiple
computer backup directories using fuzzy matching and user-guided selection.

This module re-exports the CLI app from mergy.cli for backwards compatibility
with `python mergy.py` usage.

Usage examples:
    # Basic scan
    mergy scan /path/to/computerNames

    # Scan with lower confidence threshold
    mergy scan /path/to/computerNames --min-confidence 50

    # Dry-run merge to preview changes
    mergy merge /path/to/computerNames --dry-run

    # Merge with custom log file
    mergy merge /path/to/computerNames --log-file ~/merge-2024.log

    # Verbose output for debugging
    mergy merge /path/to/computerNames --verbose
"""

from mergy.cli import app

if __name__ == "__main__":
    app()
