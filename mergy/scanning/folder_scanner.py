"""Folder scanning utility for collecting metadata.

This module provides the FolderScanner class for scanning folders and collecting
metadata about their contents, including file counts, sizes, and date ranges.

Example:
    >>> from mergy.scanning import FolderScanner
    >>> scanner = FolderScanner()
    >>> folders = scanner.scan_immediate_subdirectories(Path("/data"))
    >>> for folder in folders:
    ...     print(f"{folder.name}: {folder.file_count} files")
"""

import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Set, Tuple

from mergy.models.data_models import ComputerFolder

from .file_hasher import FileHasher


class FolderScanner:
    """Scans folders and collects metadata for ComputerFolder instances.

    This class provides methods for scanning folder contents and collecting
    metadata such as file counts, total sizes, and date ranges. It integrates
    with FileHasher for potential future hashing operations during scanning.

    The scanner skips '.merged' directories during traversal to avoid
    processing previously merged content.

    Attributes:
        _file_hasher: FileHasher instance for potential hashing operations.
        _errors: List of error messages encountered during scanning.

    Example:
        >>> scanner = FolderScanner()
        >>> folder = scanner.scan_folder(Path("/data/computer-01"))
        >>> if folder:
        ...     print(f"Found {folder.file_count} files ({folder.total_size} bytes)")
    """

    def __init__(self, file_hasher: Optional[FileHasher] = None) -> None:
        """Initialize the FolderScanner.

        Args:
            file_hasher: Optional FileHasher instance. If not provided,
                a new instance will be created.
        """
        self._file_hasher = file_hasher if file_hasher is not None else FileHasher()
        self._errors: List[str] = []

    def scan_folder(self, folder_path: Path) -> Optional[ComputerFolder]:
        """Scan a folder and collect metadata.

        Walks the entire folder tree, collecting file counts, sizes, and
        date ranges. Skips '.merged' directories during traversal.

        Args:
            folder_path: Path to the folder to scan.

        Returns:
            ComputerFolder instance with collected metadata, or None if the
            folder is inaccessible or an error occurred.

        Example:
            >>> scanner = FolderScanner()
            >>> folder = scanner.scan_folder(Path("/data/backup"))
            >>> if folder:
            ...     print(f"Oldest file: {folder.oldest_file_date}")
            ...     print(f"Newest file: {folder.newest_file_date}")
        """
        try:
            resolved_path = folder_path.resolve()

            # Validate folder exists and is a directory
            if not resolved_path.exists():
                self._errors.append(f"Folder not found: {folder_path}")
                return None

            if not resolved_path.is_dir():
                self._errors.append(f"Not a directory: {folder_path}")
                return None

            # Initialize counters and trackers
            file_count = 0
            total_size = 0
            oldest_mtime: Optional[float] = None
            newest_mtime: Optional[float] = None

            # Track visited directories by (device, inode) to detect cycles
            visited_dirs: Set[Tuple[int, int]] = set()
            # Add root directory to visited set
            root_stat = resolved_path.stat()
            visited_dirs.add((root_stat.st_dev, root_stat.st_ino))

            # Walk the folder tree (followlinks=False to avoid automatic symlink following)
            for dirpath, dirnames, filenames in os.walk(resolved_path, followlinks=False):
                # Skip .merged directories
                if ".merged" in dirnames:
                    dirnames.remove(".merged")

                # Check for directory symlinks and handle cycle detection
                dirs_to_remove = []
                for dirname in dirnames:
                    dir_full_path = Path(dirpath) / dirname
                    if dir_full_path.is_symlink():
                        try:
                            # Resolve the symlink target and check for cycles
                            target_stat = dir_full_path.stat()
                            dir_id = (target_stat.st_dev, target_stat.st_ino)
                            if dir_id in visited_dirs:
                                # Skip this directory symlink to avoid cycle
                                dirs_to_remove.append(dirname)
                            else:
                                # Mark as visited and allow traversal
                                visited_dirs.add(dir_id)
                        except OSError:
                            # If we can't stat the symlink target, skip it
                            dirs_to_remove.append(dirname)
                    else:
                        # Regular directory - track it to detect if a symlink points back
                        try:
                            dir_stat = os.stat(dir_full_path)
                            visited_dirs.add((dir_stat.st_dev, dir_stat.st_ino))
                        except OSError:
                            pass

                for dirname in dirs_to_remove:
                    dirnames.remove(dirname)

                # Process each file in current directory
                for filename in filenames:
                    file_path = Path(dirpath) / filename

                    try:
                        stat_result = file_path.stat()
                        file_count += 1
                        total_size += stat_result.st_size

                        # Track oldest and newest file modification times
                        mtime = stat_result.st_mtime
                        if oldest_mtime is None or mtime < oldest_mtime:
                            oldest_mtime = mtime
                        if newest_mtime is None or mtime > newest_mtime:
                            newest_mtime = mtime

                    except PermissionError:
                        self._errors.append(f"Permission denied: {file_path}")
                        continue
                    except OSError as e:
                        self._errors.append(f"Error accessing {file_path}: {e}")
                        continue

            # Handle empty folders - use folder's own timestamp
            if oldest_mtime is None or newest_mtime is None:
                folder_stat = resolved_path.stat()
                folder_mtime = folder_stat.st_mtime
                oldest_mtime = folder_mtime
                newest_mtime = folder_mtime

            return ComputerFolder(
                path=resolved_path,
                name=resolved_path.name,
                file_count=file_count,
                total_size=total_size,
                oldest_file_date=datetime.fromtimestamp(oldest_mtime),
                newest_file_date=datetime.fromtimestamp(newest_mtime),
            )

        except PermissionError:
            self._errors.append(f"Permission denied accessing folder: {folder_path}")
            return None
        except OSError as e:
            self._errors.append(f"Error scanning folder {folder_path}: {e}")
            return None

    def scan_immediate_subdirectories(self, base_path: Path) -> List[ComputerFolder]:
        """Scan immediate subdirectories of a base path.

        This method only scans the immediate children of the base path,
        not the base path itself or nested subdirectories at deeper levels.

        Args:
            base_path: Path to the base directory containing subdirectories.

        Returns:
            List of ComputerFolder instances for each successfully scanned
            subdirectory. Subdirectories that fail to scan are skipped
            with errors logged.

        Example:
            >>> scanner = FolderScanner()
            >>> # base_path contains: computer-01/, computer-02/, computer-03/
            >>> folders = scanner.scan_immediate_subdirectories(base_path)
            >>> print(f"Scanned {len(folders)} folders")
        """
        result: List[ComputerFolder] = []

        try:
            resolved_path = base_path.resolve()

            if not resolved_path.exists():
                self._errors.append(f"Base path not found: {base_path}")
                return result

            if not resolved_path.is_dir():
                self._errors.append(f"Base path is not a directory: {base_path}")
                return result

            # Iterate through immediate children
            for child in resolved_path.iterdir():
                # Only process directories, skip files
                if not child.is_dir():
                    continue

                # Scan each subdirectory
                folder = self.scan_folder(child)
                if folder is not None:
                    result.append(folder)

        except PermissionError:
            self._errors.append(f"Permission denied accessing base path: {base_path}")
        except OSError as e:
            self._errors.append(f"Error scanning base path {base_path}: {e}")

        return result

    def get_errors(self) -> List[str]:
        """Get list of errors encountered during scanning operations.

        Returns:
            List of error message strings.

        Example:
            >>> scanner = FolderScanner()
            >>> scanner.scan_folder(Path("/nonexistent"))
            >>> errors = scanner.get_errors()
            >>> print(errors[0])  # 'Folder not found: /nonexistent'
        """
        return self._errors.copy()

    def clear_errors(self) -> None:
        """Clear the list of accumulated errors."""
        self._errors.clear()

    @property
    def file_hasher(self) -> FileHasher:
        """Get the FileHasher instance used by this scanner.

        Returns:
            The FileHasher instance.
        """
        return self._file_hasher
