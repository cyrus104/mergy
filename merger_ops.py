"""
File operations and scanning logic for the Computer Data Organization Tool.

This module provides backward compatibility imports for:
- MergeOrchestrator: Coordinates the complete merge workflow (moved to mergy.orchestration)
- MergeLogger: Structured logging for merge operations (moved to mergy.orchestration)
- MergeTUI: Terminal UI for interactive merge operations (moved to mergy.ui)

For new code, prefer importing directly from the respective packages:
- from mergy.orchestration import MergeOrchestrator, MergeLogger
- from mergy.ui import MergeTUI
- from mergy.scanning import FileHasher, FolderScanner
- from mergy.operations import FileOperations
"""

import warnings

warnings.warn(
    "The 'merger_ops' module is deprecated and will be removed in a future version. "
    "Please import directly from the new module paths:\n"
    "  - from mergy.orchestration import MergeOrchestrator, MergeLogger\n"
    "  - from mergy.ui import MergeTUI\n"
    "  - from mergy.scanning import FileHasher, FolderScanner\n"
    "  - from mergy.operations import FileOperations",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export classes from their new locations for backward compatibility
from mergy.orchestration import MergeOrchestrator, MergeLogger
from mergy.ui import MergeTUI
from mergy.scanning import FileHasher, FolderScanner
from mergy.operations import FileOperations

__all__ = [
    "MergeOrchestrator",
    "MergeLogger",
    "MergeTUI",
    "FileHasher",
    "FolderScanner",
    "FileOperations",
]
