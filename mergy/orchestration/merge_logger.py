"""MergeLogger for logging merge operations in formatted output.

This module provides the MergeLogger class that generates structured log files
following the format specification defined in AGENTS.md section 7.1.
"""

import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional, TextIO

from mergy.models import (
    FileConflict,
    FolderMatch,
    MergeOperation,
    MergeSelection,
    MergeSummary,
)


class MergeLogger:
    """Logger for merge operations with structured output format.

    Generates log files with sections for header, scan phase, merge phase,
    and summary following the specification in AGENTS.md section 7.1.

    Usage:
        with MergeLogger(dry_run=True) as logger:
            logger.log_header()
            logger.log_scan_phase(base_path, min_confidence, total_folders, matches, filtered_count)
            for selection in selections:
                logger.log_merge_selection(selection)
                # ... perform merge ...
                logger.log_merge_operation(operation)
            logger.log_summary(summary)

    Attributes:
        SEPARATOR: The 65-character separator line used between sections.
    """

    SEPARATOR = "=" * 65

    def __init__(
        self,
        log_file_path: Optional[Path] = None,
        dry_run: bool = False,
        base_path: Optional[Path] = None,
    ) -> None:
        """Initialize the MergeLogger.

        Args:
            log_file_path: Optional path for the log file. If not provided,
                generates a timestamped filename in the current directory.
            dry_run: Whether this is a dry run (no actual changes made).
            base_path: Base path for scan operations (used in header).

        Raises:
            OSError: If the log file path is not writable.
        """
        self._dry_run = dry_run
        self._base_path = base_path
        self._start_timestamp = datetime.now()
        self._file_handle: Optional[TextIO] = None
        self._selection_counter = 0

        if log_file_path is None:
            timestamp_str = self._start_timestamp.strftime("%Y-%m-%d_%H-%M-%S")
            self._log_file_path = Path.cwd() / f"merge_log_{timestamp_str}.log"
        else:
            self._log_file_path = Path(log_file_path)

        # Validate path is writable
        self._validate_path()

    def _validate_path(self) -> None:
        """Validate that the log file path is writable.

        Raises:
            OSError: If the parent directory doesn't exist or is not writable.
        """
        parent = self._log_file_path.parent
        if not parent.exists():
            raise OSError(f"Parent directory does not exist: {parent}")
        if not parent.is_dir():
            raise OSError(f"Parent path is not a directory: {parent}")
        # Try to check write permissions
        try:
            test_file = parent / f".mergy_test_{id(self)}"
            test_file.touch()
            test_file.unlink()
        except PermissionError:
            raise OSError(f"Permission denied: cannot write to {parent}")

    def __enter__(self) -> "MergeLogger":
        """Enter the context manager, opening the log file.

        Returns:
            The MergeLogger instance.

        Raises:
            OSError: If the file cannot be opened for writing.
        """
        try:
            self._file_handle = open(self._log_file_path, "w", encoding="utf-8")
        except OSError as e:
            raise OSError(f"Cannot open log file for writing: {e}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit the context manager, closing the log file.

        Ensures the file is closed even if an exception occurred.
        """
        if self._file_handle is not None:
            try:
                self._file_handle.close()
            except Exception as e:
                print(f"Warning: Error closing log file: {e}", file=sys.stderr)
            finally:
                self._file_handle = None

    def get_log_path(self) -> Path:
        """Get the path to the log file.

        Returns:
            The path to the log file.
        """
        return self._log_file_path

    def log_header(self) -> None:
        """Write the header section to the log file.

        Writes the title, timestamp, and mode (LIVE MERGE or DRY RUN).
        """
        self._write_separator()
        self._write_line("Computer Data Organization Tool - Merge Log")
        self._write_separator()
        self._write_line(f"Timestamp: {self._format_timestamp(self._start_timestamp)}")
        mode = "DRY RUN" if self._dry_run else "LIVE MERGE"
        self._write_line(f"Mode: {mode}")
        self._write_line("")

    def log_scan_phase(
        self,
        base_path: Path,
        min_confidence: float,
        total_folders: int,
        match_groups: List[FolderMatch],
        threshold_filtered_count: int,
    ) -> None:
        """Write the scan phase section to the log file.

        Args:
            base_path: Path to the scanned directory.
            min_confidence: Confidence threshold (0.0-1.0).
            total_folders: Total number of folders scanned.
            match_groups: List of FolderMatch objects found.
            threshold_filtered_count: Number of match groups above threshold.
        """
        self._write_separator()
        self._write_line("SCAN PHASE")
        self._write_separator()
        self._write_line(f"Base Path: {base_path}")
        self._write_line(f"Minimum Confidence Threshold: {int(min_confidence * 100)}%")
        self._write_line(f"Total folders scanned: {total_folders}")
        self._write_line(f"Match groups found: {len(match_groups)}")
        self._write_line(f"Match groups above threshold: {threshold_filtered_count}")
        self._write_line("")

        if match_groups:
            self._write_line("Match Groups:")
        for i, match_group in enumerate(match_groups, start=1):
            confidence_pct = int(match_group.confidence * 100)
            match_reason = match_group.match_reason.value
            self._write_line(f"Group {i}: ({confidence_pct}% - {match_reason})")
            for folder in match_group.folders:
                self._write_line(f"- {folder.name}", indent=2)
            self._write_line("")

    def log_merge_selection(self, selection: MergeSelection) -> None:
        """Write a merge selection entry to the log file.

        Args:
            selection: The MergeSelection object to log.
        """
        if self._selection_counter == 0:
            self._write_separator()
            self._write_line("MERGE PHASE")
            self._write_separator()
            self._write_line("")

        self._selection_counter += 1
        confidence_pct = int(selection.match_group.confidence * 100)

        self._write_line(f"Selection {self._selection_counter}:")
        self._write_line(f"Confidence: {confidence_pct}%", indent=2)
        self._write_line(f"Primary: {selection.primary.name}", indent=2)
        self._write_line("Merging from:", indent=2)
        for folder in selection.merge_from:
            self._write_line(f"- {folder.name}", indent=4)
        self._write_line("")

    def log_merge_operation(
        self,
        operation: MergeOperation,
        conflicts: Optional[List[FileConflict]] = None,
    ) -> None:
        """Write a merge operation entry with statistics and conflicts.

        Args:
            operation: The MergeOperation object with statistics.
            conflicts: Optional list of FileConflict objects to log details for.
        """
        now = datetime.now()
        self._write_line(
            f"[{self._format_timestamp(now)}] Starting merge into: {operation.selection.primary.name}"
        )

        for source in operation.selection.merge_from:
            self._write_line(f"Merging: {source.name}", indent=2)
            self._write_line(f"Files copied: {operation.files_copied}", indent=4)
            self._write_line(f"Files skipped (duplicates): {operation.files_skipped}", indent=4)
            self._write_line(f"Conflicts resolved: {operation.conflicts_resolved}", indent=4)
            self._write_line(f"Empty folders removed: {operation.folders_removed}", indent=4)

        if conflicts:
            for conflict in conflicts:
                # Determine which file was kept (newer) and which was moved
                if conflict.primary_ctime >= conflict.conflict_ctime:
                    kept = "kept newer"
                    moved_hash = conflict.conflict_hash[:16]
                else:
                    kept = "kept newer"
                    moved_hash = conflict.primary_hash[:16]

                # Build the .merged filename following convention: base_hash.ext
                original_name = conflict.relative_path.name
                if "." in original_name:
                    name_part, ext = original_name.rsplit(".", 1)
                    merged_filename = f"{name_part}_{moved_hash}.{ext}"
                else:
                    merged_filename = f"{original_name}_{moved_hash}"

                merged_dir = conflict.relative_path.parent / ".merged"
                self._write_line(
                    f"! Conflict: {conflict.relative_path} - {kept}, moved older to {merged_dir}/{merged_filename}",
                    indent=4,
                )

        # Log errors from the operation
        if operation.errors:
            self._write_line("Errors:", indent=2)
            for error in operation.errors:
                self._write_line(f"- {error}", indent=4)

        end_time = datetime.now()
        self._write_line(f"[{self._format_timestamp(end_time)}] Completed merge")
        self._write_line("")

    def log_summary(self, summary: MergeSummary) -> None:
        """Write the summary section to the log file.

        Args:
            summary: The MergeSummary object with aggregated statistics.
        """
        self._write_separator()
        self._write_line("SUMMARY")
        self._write_separator()
        self._write_line(f"Total merge operations: {summary.total_operations}")
        self._write_line(f"Files copied: {summary.total_files_copied:,}")
        self._write_line(f"Files skipped (duplicates): {summary.total_files_skipped:,}")
        self._write_line(f"Conflicts resolved: {summary.total_conflicts_resolved}")
        self._write_line(f"Empty folders removed: {summary.total_folders_removed}")

        # Log errors summary
        if summary.errors:
            self._write_line(f"Total errors: {len(summary.errors)}")
            self._write_line("Errors:")
            for error in summary.errors:
                self._write_line(f"  - {error}")

        self._write_line(f"Duration: {self._format_duration(summary.duration_seconds)}")
        self._write_line("")
        self._write_line(f"Log file: {self._log_file_path}")
        self._write_separator()

    def _format_duration(self, seconds: float) -> str:
        """Format duration in human-readable format.

        Args:
            seconds: Duration in seconds.

        Returns:
            Formatted string like "5m 23s", "1h 5m 30s", or "45s".
        """
        total_seconds = int(seconds)

        if total_seconds < 60:
            return f"{total_seconds}s"

        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        secs = total_seconds % 60

        if hours > 0:
            return f"{hours}h {minutes}m {secs}s"
        else:
            return f"{minutes}m {secs}s"

    def _format_timestamp(self, dt: datetime) -> str:
        """Format a datetime as a timestamp string.

        Args:
            dt: The datetime to format.

        Returns:
            Timestamp in 'YYYY-MM-DD HH:MM:SS' format.
        """
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    def _write_separator(self) -> None:
        """Write a separator line to the log file."""
        self._write_line(self.SEPARATOR)

    def _write_line(self, text: str, indent: int = 0) -> None:
        """Write a line to the log file with optional indentation.

        Args:
            text: The text to write.
            indent: Number of spaces to indent the line.
        """
        if self._file_handle is None:
            print(
                f"Warning: Attempted to write to closed log file: {text}",
                file=sys.stderr,
            )
            return

        try:
            indented_text = " " * indent + text
            self._file_handle.write(indented_text + "\n")
        except OSError as e:
            print(f"Warning: Error writing to log file: {e}", file=sys.stderr)
