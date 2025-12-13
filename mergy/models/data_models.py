"""Core data models for the Mergy folder merging application."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List

from .match_reason import MatchReason


@dataclass(frozen=True)
class ComputerFolder:
    """Represents a scanned folder with metadata.

    Attributes:
        path: Absolute path to the folder.
        name: Display name of the folder.
        file_count: Total number of files in the folder.
        total_size: Total size of all files in bytes.
        oldest_file_date: Modification date of the oldest file.
        newest_file_date: Modification date of the newest file.
    """

    path: Path
    name: str
    file_count: int
    total_size: int
    oldest_file_date: datetime
    newest_file_date: datetime


@dataclass(frozen=True)
class FolderMatch:
    """Represents a group of matched folders.

    Attributes:
        folders: List of folders that match together.
        confidence: Match confidence score (0.0 to 1.0).
        match_reason: The tier/method that produced this match.
        base_name: The normalized base name used for matching.
    """

    folders: List[ComputerFolder]
    confidence: float
    match_reason: MatchReason
    base_name: str


@dataclass(frozen=True)
class MergeSelection:
    """Represents user's merge decision.

    Attributes:
        primary: The primary folder to merge into.
        merge_from: List of folders to merge from.
        match_group: The original match group this selection came from.
    """

    primary: ComputerFolder
    merge_from: List[ComputerFolder]
    match_group: FolderMatch


@dataclass(frozen=True)
class FileConflict:
    """Represents a file conflict during merge.

    Attributes:
        relative_path: Path relative to folder root.
        primary_file: Absolute path to file in primary folder.
        conflicting_file: Absolute path to conflicting file.
        primary_hash: Hash of the primary file.
        conflict_hash: Hash of the conflicting file.
        primary_ctime: Creation time of the primary file.
        conflict_ctime: Creation time of the conflicting file.
    """

    relative_path: Path
    primary_file: Path
    conflicting_file: Path
    primary_hash: str
    conflict_hash: str
    primary_ctime: datetime
    conflict_ctime: datetime


@dataclass(frozen=True)
class MergeOperation:
    """Tracks a single merge operation.

    Attributes:
        selection: The merge selection being executed.
        dry_run: Whether this is a dry run (no actual changes).
        timestamp: When the operation was performed.
        files_copied: Number of files copied.
        files_skipped: Number of files skipped (duplicates).
        conflicts_resolved: Number of conflicts resolved.
        folders_removed: Number of source folders removed.
        errors: List of error messages encountered.
    """

    selection: MergeSelection
    dry_run: bool
    timestamp: datetime
    files_copied: int
    files_skipped: int
    conflicts_resolved: int
    folders_removed: int
    errors: List[str]


@dataclass(frozen=True)
class MergeSummary:
    """Aggregates statistics across all merge operations.

    Attributes:
        total_operations: Total number of merge operations performed.
        total_files_copied: Total files copied across all operations.
        total_files_skipped: Total files skipped across all operations.
        total_conflicts_resolved: Total conflicts resolved.
        total_folders_removed: Total folders removed.
        duration_seconds: Total duration of all operations in seconds.
        errors: Aggregated list of all errors encountered.
    """

    total_operations: int
    total_files_copied: int
    total_files_skipped: int
    total_conflicts_resolved: int
    total_folders_removed: int
    duration_seconds: float
    errors: List[str]
