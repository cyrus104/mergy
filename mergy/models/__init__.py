"""
Models package for the Computer Data Organization Tool.

This package provides convenient imports for all data models:
- MatchReason: Enum for match rationale categories
- ComputerFolder: Folder metadata
- FolderMatch: Match between folders
- MergeSelection: User's merge selection
- FileConflict: File conflict data
- MergeOperation: Merge operation state
- MergeSummary: Merge workflow summary
"""

from .match_reason import MatchReason
from .data_models import (
    ComputerFolder,
    FolderMatch,
    MergeSelection,
    FileConflict,
    MergeOperation,
    MergeSummary,
)

__all__ = [
    "MatchReason",
    "ComputerFolder",
    "FolderMatch",
    "MergeSelection",
    "FileConflict",
    "MergeOperation",
    "MergeSummary",
]
