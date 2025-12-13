"""Mergy - Computer Data Organization Tool.

A Python application for intelligently merging folders across multiple
computer backup directories using fuzzy matching and user-guided selection.
"""

__version__ = "0.1.0"

from .models import (
    MatchReason,
    ComputerFolder,
    FileConflict,
    FolderMatch,
    MergeOperation,
    MergeSelection,
    MergeSummary,
)

__all__ = [
    "__version__",
    "MatchReason",
    "ComputerFolder",
    "FileConflict",
    "FolderMatch",
    "MergeOperation",
    "MergeSelection",
    "MergeSummary",
]


def main() -> None:
    """Entry point for the Mergy CLI application.

    This function is called when the `mergy` command is invoked after
    package installation via pip. It imports and runs the Typer app
    from the mergy.cli module.
    """
    from mergy.cli import app
    app()
