"""
Core data models for the Computer Data Organization Tool.

This module contains the following dataclasses:
- ComputerFolder: Represents a computer folder with its metadata
- FolderMatch: Represents a match between folders identified as potential duplicates
- MergeSelection: Represents the user's selection for a merge operation
- FileConflict: Represents a conflict between two files at the same relative path
- MergeOperation: Tracks the state and results of a merge operation
- MergeSummary: Summary of the merge workflow results
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from .match_reason import MatchReason


@dataclass
class ComputerFolder:
    """Represents a computer folder with its metadata."""
    path: Path                        # Full path to folder
    name: str                         # Folder name
    file_count: int                   # Total files
    total_size: int                   # Total bytes
    oldest_file_date: Optional[datetime]  # Earliest file creation (None if empty folder)
    newest_file_date: Optional[datetime]  # Latest file creation (None if empty folder)


@dataclass
class FolderMatch:
    """Represents a match between folders identified as potential duplicates."""
    folders: List[ComputerFolder]     # Matched folders
    confidence: float                 # Match confidence (0-100)
    match_reason: MatchReason         # Which tier matched
    base_name: str                    # Common base name


@dataclass
class MergeSelection:
    """Represents the user's selection for a merge operation."""
    primary: ComputerFolder           # Destination folder
    merge_from: List[ComputerFolder]  # Source folders
    match_group: FolderMatch          # Original match


@dataclass
class FileConflict:
    """Represents a conflict between two files at the same relative path."""
    relative_path: Path               # Path within folder
    primary_file: Path                # Primary file location
    conflicting_file: Path            # Conflicting file location
    primary_hash: str                 # SHA256 of primary
    conflict_hash: str                # SHA256 of conflict
    primary_ctime: datetime           # Primary creation time
    conflict_ctime: datetime          # Conflict creation time


@dataclass
class MergeOperation:
    """Tracks the state and results of a merge operation."""
    selection: MergeSelection         # User selection
    dry_run: bool                     # Dry run mode flag
    timestamp: datetime               # Operation start time
    files_copied: int = 0             # New files copied
    files_skipped: int = 0            # Duplicate files skipped
    conflicts_resolved: int = 0       # Conflicts handled
    folders_removed: int = 0          # Empty folders cleaned
    errors: List[str] = field(default_factory=list)  # Error messages


@dataclass
class MergeSummary:
    """Summary of the merge workflow results returned by MergeOrchestrator."""
    total_operations: int = 0         # Number of merge operations performed
    files_copied: int = 0             # Total files copied across all operations
    files_skipped: int = 0            # Total duplicate files skipped
    conflicts_resolved: int = 0       # Total conflicts handled
    folders_removed: int = 0          # Total empty folders cleaned
    errors: List[str] = field(default_factory=list)  # All error messages
    duration: float = 0.0             # Total workflow duration in seconds
    interrupted: bool = False         # Whether the workflow was interrupted by user
