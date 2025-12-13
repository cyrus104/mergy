"""
File operations module for the Computer Data Organization Tool.

This module contains the FileOperations class for safe file manipulation
during merge operations.
"""

import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from rich.progress import Progress, TaskID

from mergy.models import ComputerFolder, MergeSelection, FileConflict, MergeOperation
from mergy.scanning import FileHasher

# Configure module logger
logger = logging.getLogger('merger_ops')


class FileOperations:
    """
    Handles safe file manipulation for merge operations.

    Provides file copying, conflict detection and resolution, and empty
    directory cleanup. All operations support dry-run mode for testing.
    """

    # Directory name for merged/archived files
    MERGED_DIR_NAME = ".merged"

    def __init__(self, file_hasher: FileHasher, dry_run: bool = False) -> None:
        """
        Create a FileOperations instance configured with a FileHasher and optional dry-run mode.
        
        Parameters:
            file_hasher (FileHasher): Used to compute file hashes during merge and conflict detection.
            dry_run (bool): If True, simulate operations without making filesystem changes.
        """
        self.file_hasher = file_hasher
        self.dry_run = dry_run

    def merge_folders(self, selection: MergeSelection) -> MergeOperation:
        """
        Perform a full merge of all merge-from folders into the primary folder described by `selection`.
        
        Parameters:
            selection (MergeSelection): Selection containing the primary folder and one or more merge-from folders.
        
        Returns:
            MergeOperation: Aggregated results and statistics for the completed merge (respecting the instance's dry-run setting).
        """
        operation = MergeOperation(
            selection=selection,
            dry_run=self.dry_run,
            timestamp=datetime.now()
        )

        primary_folder = selection.primary.path

        # Process each merge-from folder
        for source_folder in selection.merge_from:
            self._merge_single_folder(
                source_folder.path,
                primary_folder,
                operation
            )

        # Remove empty directories from merge-from folders
        if self.dry_run:
            # In dry-run mode, count directories that would be removed
            for source_folder in selection.merge_from:
                count = self._count_empty_dirs(source_folder.path)
                operation.folders_removed += count
        else:
            for source_folder in selection.merge_from:
                removed = self._remove_empty_dirs(source_folder.path)
                operation.folders_removed += removed

        return operation

    def _merge_single_folder(
        self,
        source_folder: Path,
        primary_folder: Path,
        operation: MergeOperation
    ) -> None:
        """
        Merge files from a single source folder into the primary folder.
        
        Recursively walks source_folder (following symlinks) and processes each file into the corresponding location in primary_folder, skipping any directories named ".merged". The provided MergeOperation is updated with counts and error messages. PermissionError conditions are recorded on the operation; an OSError indicating "No space left on device" (errno 28) is recorded and re-raised to abort the merge, while other OSErrors are recorded and the merge continues.
        
        Parameters:
            source_folder (Path): Source folder to merge from.
            primary_folder (Path): Destination primary folder.
            operation (MergeOperation): Operation object that will be mutated to record files copied, skipped, conflicts resolved, and any errors.
        
        Raises:
            OSError: Re-raises when disk is full (errno 28 or error message contains "No space left on device") to abort the operation.
        """
        # Walk the source folder tree
        for root, dirs, files in os.walk(source_folder, followlinks=True):
            root_path = Path(root)

            # Skip .merged directories
            dirs[:] = [d for d in dirs if d != self.MERGED_DIR_NAME]

            for filename in files:
                source_file = root_path / filename

                # Calculate relative path from source folder root
                relative_path = source_file.relative_to(source_folder)

                # Construct destination path in primary folder
                dest_file = primary_folder / relative_path

                try:
                    self._process_file(
                        source_file,
                        dest_file,
                        relative_path,
                        primary_folder,
                        operation
                    )
                except PermissionError as e:
                    error_msg = f"Permission denied: {source_file} - {e}"
                    logger.warning(error_msg)
                    operation.errors.append(error_msg)
                except OSError as e:
                    if "No space left on device" in str(e) or e.errno == 28:
                        error_msg = f"Disk full - aborting merge operation: {e}"
                        logger.critical(error_msg)
                        operation.errors.append(error_msg)
                        raise  # Re-raise to abort the operation
                    else:
                        error_msg = f"Error processing {source_file}: {e}"
                        logger.warning(error_msg)
                        operation.errors.append(error_msg)

    def _process_file(
        self,
        source_file: Path,
        dest_file: Path,
        relative_path: Path,
        primary_folder: Path,
        operation: MergeOperation
    ) -> None:
        """
        Process a single file from a merge source by copying it into the primary, skipping it if identical, or resolving a conflict if different.
        
        This updates the provided MergeOperation counters: increments files_copied when a new file is copied, files_skipped when the file is identical to the primary, and conflicts_resolved when a differing file is resolved. Side effects include creating or moving files and creating a `.merged` preservation directory when resolving conflicts (subject to dry-run mode).
        
        Parameters:
            source_file (Path): Path to the file in the merge-from folder.
            dest_file (Path): Corresponding path in the primary folder.
            relative_path (Path): File path relative to the root of the source folder (used for logging and preserved-path construction).
            primary_folder (Path): Root path of the primary folder where files are merged into.
            operation (MergeOperation): Operation accumulator that will be updated with counts and any errors.
        """
        if not dest_file.exists():
            # File doesn't exist in primary - copy it
            self._copy_file(source_file, dest_file)
            operation.files_copied += 1
            logger.debug(f"Copied new file: {relative_path}")
        else:
            # File exists - compare hashes
            conflict = self._compare_files(dest_file, source_file, relative_path)

            if conflict is None:
                # Hashes match - skip (duplicate)
                operation.files_skipped += 1
                logger.debug(f"Skipped duplicate: {relative_path}")
            else:
                # Hashes differ - resolve conflict
                self._resolve_conflict(conflict, primary_folder)
                operation.conflicts_resolved += 1
                logger.debug(f"Resolved conflict: {relative_path}")

    def _compare_files(
        self,
        primary_path: Path,
        merge_path: Path,
        relative_path: Path
    ) -> Optional[FileConflict]:
        """
        Detects whether two files conflict by comparing their content hashes.
        
        Parameters:
            primary_path (Path): Path to the file in the primary folder.
            merge_path (Path): Path to the file in the merge-from folder.
            relative_path (Path): Relative path of the file within the folder structure.
        
        Returns:
            FileConflict: Details of the conflict including `relative_path`, `primary_file`, `conflicting_file`,
                `primary_hash`, `conflict_hash`, `primary_ctime`, and `conflict_ctime` when the files differ.
            None: If the files are identical or if either file's hash cannot be computed (comparison is skipped).
        """
        primary_hash = self.file_hasher.get_hash(primary_path)
        merge_hash = self.file_hasher.get_hash(merge_path)

        # Handle hash calculation errors
        if not primary_hash or not merge_hash:
            logger.warning(f"Could not compare files: {relative_path}")
            return None

        if primary_hash == merge_hash:
            # Files are identical
            return None

        # Files differ - create conflict
        primary_stat = primary_path.stat()
        merge_stat = merge_path.stat()

        return FileConflict(
            relative_path=relative_path,
            primary_file=primary_path,
            conflicting_file=merge_path,
            primary_hash=primary_hash,
            conflict_hash=merge_hash,
            primary_ctime=datetime.fromtimestamp(primary_stat.st_ctime),
            conflict_ctime=datetime.fromtimestamp(merge_stat.st_ctime)
        )

    def _resolve_conflict(self, conflict: FileConflict, primary_folder: Path) -> None:
        """
        Resolve a file conflict by preserving the older version in a nearby .merged directory.
        
        Determines the newer file by comparing ctime; the newer file remains in the primary location
        and the older file is preserved next to the conflicted path inside a ".merged" subdirectory
        with a short hash appended to its filename. When running in dry-run mode, no filesystem
        changes are made but the same resolution decision is performed.
        
        Parameters:
            conflict (FileConflict): Details of the conflicting files, their hashes, ctimes, and relative path.
            primary_folder (Path): Root path of the primary folder used to locate or create the adjacent ".merged" directory.
        """
        # Determine which file is newer based on ctime
        primary_is_newer = conflict.primary_ctime >= conflict.conflict_ctime

        if primary_is_newer:
            # Primary is newer - move merge-from file to .merged/ in primary
            file_to_preserve = conflict.conflicting_file
            hash_to_use = conflict.conflict_hash[:16]
        else:
            # Merge-from is newer - move primary to .merged/, copy merge-from to primary
            file_to_preserve = conflict.primary_file
            hash_to_use = conflict.primary_hash[:16]

        # Construct path for preserved file in .merged/ directory
        relative_dir = conflict.relative_path.parent
        original_name = conflict.relative_path.name

        # Create new filename with hash suffix
        stem = conflict.relative_path.stem
        suffix = conflict.relative_path.suffix
        preserved_name = f"{stem}_{hash_to_use}{suffix}"

        # .merged/ directory at the same level as the conflicting file
        merged_dir = primary_folder / relative_dir / self.MERGED_DIR_NAME
        preserved_path = merged_dir / preserved_name

        if not self.dry_run:
            # Create .merged/ directory if needed
            merged_dir.mkdir(parents=True, exist_ok=True)

            if primary_is_newer:
                # Copy merge-from file to .merged/
                shutil.copy2(file_to_preserve, preserved_path)
            else:
                # Move primary file to .merged/, then copy merge-from to primary
                shutil.move(str(conflict.primary_file), str(preserved_path))
                shutil.copy2(conflict.conflicting_file, conflict.primary_file)

        logger.info(
            f"Conflict resolved: {conflict.relative_path} - "
            f"preserved older version to {preserved_path.name}"
        )

    def _copy_file(self, source: Path, dest: Path) -> None:
        """
        Copy a file to the destination, creating parent directories as needed and preserving file metadata.
        
        If the FileOperations instance is in dry-run mode, the intended copy is logged and no filesystem changes are made.
        
        Parameters:
            source (Path): Path to the source file to copy.
            dest (Path): Path to the destination file to create or overwrite.
        """
        if self.dry_run:
            logger.debug(f"[DRY RUN] Would copy: {source} -> {dest}")
            return

        # Create parent directories if needed
        dest.parent.mkdir(parents=True, exist_ok=True)

        # Copy file preserving metadata
        shutil.copy2(source, dest)

    def _remove_empty_dirs(self, folder_path: Path) -> int:
        """
        Remove empty subdirectories under the given folder, skipping any directories named ".merged".
        
        Performs a bottom-up traversal and removes directories that are empty after their children are processed. Does nothing in dry-run mode, ignores directories named ".merged", and silently skips directories that cannot be removed due to permissions or concurrent content changes. After traversal, attempts to remove the root folder if it is empty.
        
        Parameters:
            folder_path (Path): Root folder to clean up.
        
        Returns:
            int: Number of directories removed.
        """
        removed_count = 0

        if self.dry_run:
            return removed_count

        # Walk bottom-up to remove empty directories
        for root, dirs, files in os.walk(folder_path, topdown=False):
            root_path = Path(root)

            # Skip if this is a .merged directory
            if root_path.name == self.MERGED_DIR_NAME:
                continue

            # Try to remove if directory is empty
            if not files and not dirs:
                try:
                    root_path.rmdir()
                    removed_count += 1
                    logger.debug(f"Removed empty directory: {root_path}")
                except OSError:
                    # Directory not empty or permission error - skip
                    pass

        # Try to remove the root folder itself if empty
        try:
            if not any(folder_path.iterdir()):
                folder_path.rmdir()
                removed_count += 1
                logger.debug(f"Removed empty root directory: {folder_path}")
        except OSError:
            pass

        return removed_count

    def _count_empty_dirs(self, folder_path: Path) -> int:
        """
        Count empty directories that would be removed without actually deleting them.

        Traverses the directory tree in the same way as _remove_empty_dirs but only
        counts directories that are currently empty, without calling rmdir().

        Args:
            folder_path: Root folder to analyze.

        Returns:
            Number of directories that would be removed.
        """
        empty_count = 0

        # Walk bottom-up to identify empty directories
        for root, dirs, files in os.walk(folder_path, topdown=False):
            root_path = Path(root)

            # Skip if this is a .merged directory
            if root_path.name == self.MERGED_DIR_NAME:
                continue

            # Count if directory is empty
            if not files and not dirs:
                empty_count += 1

        # Check if the root folder itself would be empty
        try:
            if not any(folder_path.iterdir()):
                empty_count += 1
        except OSError:
            pass

        return empty_count