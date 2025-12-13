"""
Backward compatibility shim for the Computer Data Organization Tool.

This module re-exports classes from their new locations for backward compatibility:
- FolderMatcher is imported from mergy.matching
- Data models are imported from mergy.models

New code should import directly from the new module paths:
- from mergy.matching import FolderMatcher
- from mergy.models import ComputerFolder, FolderMatch, MatchReason, etc.
"""

import warnings

warnings.warn(
    "The 'merger_models' module is deprecated and will be removed in a future version. "
    "Please import directly from the new module paths:\n"
    "  - from mergy.models import ComputerFolder, FolderMatch, MergeSelection, FileConflict, MergeOperation, MergeSummary, MatchReason\n"
    "  - from mergy.matching import FolderMatcher",
    DeprecationWarning,
    stacklevel=2,
)

from mergy.matching import FolderMatcher
from mergy.models.match_reason import MatchReason
from mergy.models.data_models import (
    ComputerFolder,
    FolderMatch,
    MergeSelection,
    FileConflict,
    MergeOperation,
    MergeSummary,
)

__all__ = [
    "FolderMatcher",
    "MatchReason",
    "ComputerFolder",
    "FolderMatch",
    "MergeSelection",
    "FileConflict",
    "MergeOperation",
    "MergeSummary",
]
