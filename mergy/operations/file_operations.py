"""File operations for merging folders.

This module provides the FileOperations class for executing merge operations,
including file copying, conflict detection, conflict resolution, and empty
directory cleanup.

Example:
    >>> from mergy.operations import FileOperations
    >>> from mergy.models import MergeSelection
    >>> ops = FileOperations()
    >>> result = ops.merge_folders(selection, dry_run=False)
    >>> print(f"Copied: {result.files_copied}, Conflicts: {result.conflicts_resolved}")
"""

import errno
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from mergy.models import FileConflict, MergeOperation, MergeSelection
from mergy.scanning import FileHasher


# Length of hash suffix used in merged file names
HASH_SUFFIX_LENGTH = 16

# Name of the directory where conflicting files are stored
MERGED_DIR_NAME = ".merged"


class FileOperations:
    """Executes file merge operations with conflict resolution.

    This class provides the core functionality for merging folders, including:
    - Copying new files from source folders to the primary folder
    - Detecting duplicates via SHA256 hash comparison
    - Resolving conflicts by keeping newer files and archiving older ones
    - Cleaning up empty directories after merge operations

    The class supports dry-run mode for previewing operations without making
    changes, and provides progress tracking via callbacks.

    Attributes:
        _hasher: FileHasher instance for computing file hashes.
        _errors: List of error messages encountered during operations.
        _progress_callback: Optional callback for progress tracking.
        _dry_run: Whether currently in dry-run mode.

    Example:
        >>> ops = FileOperations()
        >>> result = ops.merge_folders(selection, dry_run=True)
        >>> print(f"Would copy {result.files_copied} files")
        >>> print(f"Would resolve {result.conflicts_resolved} conflicts")
    """

    def __init__(
        self,
        hasher: Optional[FileHasher] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> None:
        """Initialize FileOperations.

        Args:
            hasher: Optional FileHasher instance. If not provided, a new one
                is created.
            progress_callback: Optional callback function invoked before
                processing each file. Signature: (current_index, total_files,
                current_file_name) -> None.
        """
        self._hasher = hasher if hasher is not None else FileHasher()
        self._errors: List[str] = []
        self._progress_callback = progress_callback
        self._dry_run = False

    def merge_folders(
        self, selection: MergeSelection, dry_run: bool = False
    ) -> MergeOperation:
        """Execute a complete merge operation.

        Merges all files from the source folders into the primary folder,
        handling duplicates and conflicts according to the spec:
        - Duplicate files (same hash) are skipped
        - Conflicting files (same path, different hash) are resolved by
          keeping the newer file and moving the older to .merged/
        - New files are copied to the primary folder
        - Empty directories are cleaned up after merging

        Args:
            selection: The MergeSelection specifying primary and source folders.
            dry_run: If True, simulate the operation without making changes.

        Returns:
            MergeOperation with statistics and any errors encountered.

        Raises:
            OSError: If a critical error occurs (e.g., disk full).
        """
        self._dry_run = dry_run
        self._errors.clear()
        start_time = datetime.now()

        files_copied = 0
        files_skipped = 0
        conflicts_resolved = 0
        folders_removed = 0

        primary_folder = selection.primary.path

        # Collect all files from all source folders first for progress tracking
        all_files: List[Tuple[Path, Path, Path]] = []  # (source_folder, abs_path, rel_path)
        for source_folder in selection.merge_from:
            for abs_path, rel_path in self._walk_files(source_folder.path):
                all_files.append((source_folder.path, abs_path, rel_path))

        total_files = len(all_files)

        # Process each file
        for idx, (source_folder, source_abs, source_rel) in enumerate(all_files):
            # Invoke progress callback
            if self._progress_callback is not None:
                self._progress_callback(idx, total_files, str(source_rel))

            primary_file = primary_folder / source_rel

            if primary_file.exists():
                # File exists in primary - check if duplicate or conflict
                conflict = self._detect_conflict(primary_file, source_abs, source_rel)

                if conflict is None:
                    # Same hash (duplicate) or error detecting conflict
                    files_skipped += 1
                else:
                    # Different content - resolve conflict
                    if self._resolve_conflict(conflict, primary_folder, dry_run):
                        conflicts_resolved += 1
                    else:
                        files_skipped += 1
            else:
                # New file - copy to primary
                if self._copy_file(source_abs, primary_file, dry_run):
                    files_copied += 1

        # Clean up empty directories in source folders
        for source_folder in selection.merge_from:
            removed = self._cleanup_empty_dirs(source_folder.path, dry_run)
            folders_removed += removed

        return MergeOperation(
            selection=selection,
            dry_run=dry_run,
            timestamp=start_time,
            files_copied=files_copied,
            files_skipped=files_skipped,
            conflicts_resolved=conflicts_resolved,
            folders_removed=folders_removed,
            errors=self._errors.copy(),
        )

    def get_errors(self) -> List[str]:
        """Get list of errors encountered during operations.

        Returns:
            Copy of the error list.
        """
        return self._errors.copy()

    def clear_errors(self) -> None:
        """Clear the list of accumulated errors."""
        self._errors.clear()

    def _copy_file(self, source: Path, dest: Path, dry_run: bool) -> bool:
        """Copy a file from source to destination.

        Creates parent directories as needed. Preserves file metadata
        (timestamps) using shutil.copy2.

        Args:
            source: Source file path.
            dest: Destination file path.
            dry_run: If True, validate but don't actually copy.

        Returns:
            True if successful (or would be in dry-run), False on error.

        Raises:
            OSError: If disk is full (critical error, operation should abort).
        """
        try:
            if dry_run:
                # Validate source exists and is readable
                if not source.exists():
                    self._errors.append(f"File not found: {source}")
                    return False
                # Verify source is readable
                if not os.access(source, os.R_OK):
                    self._errors.append(f"Permission denied: {source}")
                    return False
                # Verify destination parent is creatable/writable
                # Find the first existing ancestor of dest.parent
                existing_ancestor = dest.parent
                while not existing_ancestor.exists():
                    existing_ancestor = existing_ancestor.parent
                if not os.access(existing_ancestor, os.W_OK):
                    self._errors.append(
                        f"Cannot write to destination directory: {existing_ancestor}"
                    )
                    return False
                return True

            # Create parent directories if needed
            dest.parent.mkdir(parents=True, exist_ok=True)

            # Copy file preserving metadata
            shutil.copy2(source, dest)
            return True

        except PermissionError:
            self._errors.append(f"Permission denied: {source}")
            return False
        except FileNotFoundError:
            self._errors.append(f"File not found: {source}")
            return False
        except OSError as e:
            if e.errno == errno.ENOSPC:
                self._errors.append(f"Disk full while copying {source} to {dest}")
                raise
            self._errors.append(f"OS error copying {source}: {e}")
            return False

    def _detect_conflict(
        self, primary_file: Path, source_file: Path, relative_path: Path
    ) -> Optional[FileConflict]:
        """Detect if two files are in conflict.

        Files are in conflict if they have different content (different hashes).
        If hashes match, they are duplicates, not conflicts.

        Args:
            primary_file: Path to file in primary folder.
            source_file: Path to file in source folder.
            relative_path: The relative path from the source folder root,
                preserving nested directory structure.

        Returns:
            FileConflict if files differ, None if they are duplicates or
            if an error occurred during hash computation.
        """
        # Compute hashes
        primary_hash = self._hasher.hash_file(primary_file)
        if primary_hash is None:
            self._errors.append(f"Failed to compute hash for {primary_file}")
            return None

        source_hash = self._hasher.hash_file(source_file)
        if source_hash is None:
            self._errors.append(f"Failed to compute hash for {source_file}")
            return None

        # Same hash = duplicate, not conflict
        if primary_hash == source_hash:
            return None

        # Different hashes - get creation times
        try:
            primary_stat = primary_file.stat()
            source_stat = source_file.stat()
        except OSError as e:
            self._errors.append(f"Failed to stat files: {e}")
            return None

        return FileConflict(
            relative_path=relative_path,
            primary_file=primary_file,
            conflicting_file=source_file,
            primary_hash=primary_hash,
            conflict_hash=source_hash,
            primary_ctime=datetime.fromtimestamp(primary_stat.st_ctime),
            conflict_ctime=datetime.fromtimestamp(source_stat.st_ctime),
        )

    def _resolve_conflict(
        self, conflict: FileConflict, primary_folder: Path, dry_run: bool
    ) -> bool:
        """Resolve a file conflict by keeping the newer file.

        The older file is moved to a .merged/ subdirectory with a hash suffix
        in its name. The .merged/ directory is created at the same level as
        the conflicting file.

        Args:
            conflict: The FileConflict to resolve.
            primary_folder: Path to the primary folder.
            dry_run: If True, validate but don't actually move/copy files.

        Returns:
            True if successful (or would be in dry-run), False on error.

        Raises:
            OSError: If disk is full (critical error).
        """
        try:
            # Determine which file is newer
            primary_is_newer = conflict.primary_ctime >= conflict.conflict_ctime

            if primary_is_newer:
                # Keep primary, move source to .merged/
                older_file = conflict.conflicting_file
                older_hash = conflict.conflict_hash
            else:
                # Source is newer - move primary to .merged/, copy source to primary
                older_file = conflict.primary_file
                older_hash = conflict.primary_hash

            # Determine .merged/ directory location (same level as conflicting file)
            merged_dir = conflict.primary_file.parent / MERGED_DIR_NAME

            # Generate new filename with hash suffix
            older_name = older_file.name
            name_parts = older_name.rsplit(".", 1)
            hash_suffix = older_hash[:HASH_SUFFIX_LENGTH]

            if len(name_parts) == 2:
                # Has extension
                new_name = f"{name_parts[0]}_{hash_suffix}.{name_parts[1]}"
            else:
                # No extension
                new_name = f"{older_name}_{hash_suffix}"

            merged_path = merged_dir / new_name

            if dry_run:
                # Verify both conflict files exist
                if not conflict.primary_file.exists():
                    self._errors.append(
                        f"Primary file not found: {conflict.primary_file}"
                    )
                    return False
                if not conflict.conflicting_file.exists():
                    self._errors.append(
                        f"Conflicting file not found: {conflict.conflicting_file}"
                    )
                    return False
                # Verify .merged/ directory can be created (check parent writability)
                merged_parent = merged_dir.parent
                if not os.access(merged_parent, os.W_OK):
                    self._errors.append(
                        f"Cannot create .merged directory in: {merged_parent}"
                    )
                    return False
                return True

            # Create .merged/ directory
            merged_dir.mkdir(parents=True, exist_ok=True)

            if primary_is_newer:
                # Move source file to .merged/
                shutil.move(str(older_file), str(merged_path))
            else:
                # Move primary to .merged/, then copy source to primary location
                shutil.move(str(conflict.primary_file), str(merged_path))
                shutil.copy2(conflict.conflicting_file, conflict.primary_file)

            return True

        except PermissionError:
            self._errors.append(
                f"Permission denied resolving conflict for {conflict.relative_path}"
            )
            return False
        except FileNotFoundError:
            self._errors.append(
                f"File not found resolving conflict for {conflict.relative_path}"
            )
            return False
        except OSError as e:
            if e.errno == errno.ENOSPC:
                self._errors.append(
                    f"Disk full resolving conflict for {conflict.relative_path}"
                )
                raise
            self._errors.append(
                f"Failed to resolve conflict for {conflict.relative_path}: {e}"
            )
            return False

    def _cleanup_empty_dirs(self, folder: Path, dry_run: bool) -> int:
        """Remove empty directories from a folder.

        Walks the folder bottom-up and removes directories that are empty
        (no files, no subdirectories). Never removes .merged/ directories.

        Args:
            folder: Root folder to clean up.
            dry_run: If True, count but don't actually remove directories.

        Returns:
            Number of directories removed (or would be removed in dry-run).
        """
        removed_count = 0

        try:
            # Walk bottom-up to remove nested empty dirs first
            for dirpath, dirnames, filenames in os.walk(folder, topdown=False):
                current_dir = Path(dirpath)

                # Skip .merged directories
                if current_dir.name == MERGED_DIR_NAME:
                    continue

                # Skip the root folder itself
                if current_dir == folder:
                    continue

                # Check if directory is empty (no files, no remaining subdirs)
                # After bottom-up walk, subdirs would have been removed if empty
                try:
                    contents = list(current_dir.iterdir())
                    if not contents:
                        if not dry_run:
                            current_dir.rmdir()
                        removed_count += 1
                except OSError as e:
                    self._errors.append(f"Error checking directory {current_dir}: {e}")

        except OSError as e:
            self._errors.append(f"Error walking directory {folder}: {e}")

        return removed_count

    def _walk_files(self, folder: Path) -> List[Tuple[Path, Path]]:
        """Walk a folder and return all files with their relative paths.

        Skips .merged/ directories during traversal.

        Args:
            folder: Root folder to walk.

        Returns:
            List of (absolute_path, relative_path) tuples for each file.
        """
        result: List[Tuple[Path, Path]] = []

        try:
            for dirpath, dirnames, filenames in os.walk(folder):
                # Skip .merged directories
                if MERGED_DIR_NAME in dirnames:
                    dirnames.remove(MERGED_DIR_NAME)

                current_dir = Path(dirpath)

                for filename in filenames:
                    abs_path = current_dir / filename
                    rel_path = abs_path.relative_to(folder)
                    result.append((abs_path, rel_path))

        except OSError as e:
            self._errors.append(f"Error walking directory {folder}: {e}")

        return result
