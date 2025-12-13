"""
Directory scanning for metadata collection in the Computer Data Organization Tool.

This module provides FolderScanner class for scanning directories to collect
metadata and create ComputerFolder instances for folder matching.
"""

from pathlib import Path
from typing import List, Optional
from datetime import datetime
import os
import logging

from mergy.models import ComputerFolder

# Configure module logger
logger = logging.getLogger(__name__)


class FolderScanner:
    """
    Scans directories to collect metadata and create ComputerFolder instances.

    Scans immediate subdirectories of a base path and collects file counts,
    sizes, and creation timestamps for each folder.
    """

    # Directory name for merged/archived files
    MERGED_DIR_NAME = ".merged"

    def __init__(self, base_path: Path) -> None:
        """
        Initialize with base directory path.

        Args:
            base_path: Base directory containing folders to scan.

        Raises:
            ValueError: If base_path does not exist or is not a directory.
        """
        if not base_path.exists():
            raise ValueError(f"Base path does not exist: {base_path}")
        if not base_path.is_dir():
            raise ValueError(f"Base path is not a directory: {base_path}")

        self.base_path = base_path.resolve()
        self._errors: List[str] = []

    @property
    def errors(self) -> List[str]:
        """Return list of errors encountered during scanning."""
        return self._errors.copy()

    def scan(self) -> List[ComputerFolder]:
        """
        Scan all subdirectories and return list of ComputerFolder objects.

        Returns:
            List of ComputerFolder instances for each valid subdirectory.
        """
        self._errors.clear()
        folders: List[ComputerFolder] = []

        try:
            for entry in self.base_path.iterdir():
                if entry.is_dir() and not self._should_skip(entry):
                    try:
                        folder = self._scan_folder(entry)
                        folders.append(folder)
                    except PermissionError:
                        error_msg = f"Permission denied scanning folder: {entry}"
                        logger.warning(error_msg)
                        self._errors.append(error_msg)
                    except OSError as e:
                        error_msg = f"Error scanning folder {entry}: {e}"
                        logger.warning(error_msg)
                        self._errors.append(error_msg)
        except PermissionError:
            error_msg = f"Permission denied accessing base path: {self.base_path}"
            logger.error(error_msg)
            self._errors.append(error_msg)

        return folders

    def _scan_folder(self, folder_path: Path) -> ComputerFolder:
        """
        Scan single folder and collect metadata.

        Args:
            folder_path: Path to the folder to scan.

        Returns:
            ComputerFolder instance with collected metadata.
        """
        file_count = 0
        total_size = 0
        oldest_ctime: Optional[float] = None
        newest_ctime: Optional[float] = None

        # Walk the folder tree recursively
        for root, dirs, files in os.walk(folder_path, followlinks=True):
            root_path = Path(root)

            # Skip .merged directories during traversal
            dirs[:] = [d for d in dirs if not self._should_skip(root_path / d)]

            for filename in files:
                file_path = root_path / filename

                try:
                    stat_info = file_path.stat()

                    file_count += 1
                    total_size += stat_info.st_size

                    ctime = stat_info.st_ctime
                    if oldest_ctime is None or ctime < oldest_ctime:
                        oldest_ctime = ctime
                    if newest_ctime is None or ctime > newest_ctime:
                        newest_ctime = ctime

                except PermissionError:
                    error_msg = f"Permission denied accessing file: {file_path}"
                    logger.warning(error_msg)
                    self._errors.append(error_msg)
                except FileNotFoundError:
                    # File may have been deleted during scan
                    pass
                except OSError as e:
                    error_msg = f"Error accessing file {file_path}: {e}"
                    logger.warning(error_msg)
                    self._errors.append(error_msg)

        # Convert timestamps to datetime objects (None if no files found)
        oldest_date: Optional[datetime] = None
        newest_date: Optional[datetime] = None
        if oldest_ctime is not None:
            oldest_date = datetime.fromtimestamp(oldest_ctime)
        if newest_ctime is not None:
            newest_date = datetime.fromtimestamp(newest_ctime)

        return ComputerFolder(
            path=folder_path,
            name=folder_path.name,
            file_count=file_count,
            total_size=total_size,
            oldest_file_date=oldest_date,
            newest_file_date=newest_date
        )

    def _should_skip(self, path: Path) -> bool:
        """
        Check if path should be skipped during scanning.

        Args:
            path: Path to check.

        Returns:
            True if path should be skipped, False otherwise.
        """
        return path.name == self.MERGED_DIR_NAME
