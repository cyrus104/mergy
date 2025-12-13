"""Data models package for Mergy.

This package contains all data structures used throughout the application.
"""

from .match_reason import MatchReason
from .data_models import (
    ComputerFolder,
    FileConflict,
    FolderMatch,
    MergeOperation,
    MergeSelection,
    MergeSummary,
)

__all__ = [
    "MatchReason",
    "ComputerFolder",
    "FileConflict",
    "FolderMatch",
    "MergeOperation",
    "MergeSelection",
    "MergeSummary",
]
