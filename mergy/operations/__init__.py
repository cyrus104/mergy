"""File operations package for Mergy.

This package provides the FileOperations class for executing merge operations,
including file copying, conflict detection and resolution, and empty directory
cleanup.

Example:
    >>> from mergy.operations import FileOperations
    >>> from mergy.models import MergeSelection
    >>> ops = FileOperations()
    >>> result = ops.merge_folders(selection, dry_run=False)
    >>> print(f"Copied: {result.files_copied}, Conflicts: {result.conflicts_resolved}")
"""

from .file_operations import FileOperations

__all__ = ["FileOperations"]
