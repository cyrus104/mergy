"""
Merge logger for the Computer Data Organization Tool.

This module contains the MergeLogger class which provides structured logging
for merge operations as specified in AGENTS.md section 7. The logger outputs
timestamped sections for scan, selection, merge progress, and summary phases.
"""

from pathlib import Path
from typing import List, Optional
from datetime import datetime

from mergy.models import ComputerFolder, FolderMatch, MergeSelection, MergeOperation


class MergeLogger:
    """
    Structured logging for merge operations.

    Implements the log format specified in AGENTS.md section 7, with
    timestamped sections for scan, selection, merge progress, and summary.
    """

    SEPARATOR = "================================================================="

    def __init__(
        self,
        log_file_path: Optional[Path] = None,
        mode: str = "LIVE MERGE"
    ) -> None:
        """
        Initialize logger with file path and mode.

        Args:
            log_file_path: Path for log file. If None, generates default name.
            mode: Operation mode - "LIVE MERGE" or "DRY RUN".
        """
        if log_file_path is None:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            log_file_path = Path(f"merge_log_{timestamp}.log")

        self.log_file_path = Path(log_file_path).resolve()
        self.mode = mode
        self._file_handle: Optional[object] = None
        self._merge_phase_started: bool = False

        # Open log file and write header
        self._file_handle = open(self.log_file_path, 'w', encoding='utf-8')
        self._write_header()

    def _write_header(self) -> None:
        """Write log file header with title, timestamp, and mode."""
        self._write_separator()
        self._write_line("COMPUTER DATA ORGANIZATION TOOL - MERGE LOG")
        self._write_separator()
        self._write_line(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self._write_line(f"Mode: {self.mode}")
        self._write_line("")

    def _write_separator(self) -> None:
        """Write separator line."""
        self._write_line(self.SEPARATOR)

    def _write_line(self, text: str) -> None:
        """Write a line to the log file."""
        if self._file_handle:
            self._file_handle.write(text + "\n")

    def _format_duration(self, seconds: float) -> str:
        """
        Format duration in seconds to human-readable string.

        Args:
            seconds: Duration in seconds.

        Returns:
            Formatted string (e.g., "2m 30s", "45s", "1h 5m 20s").
        """
        if seconds < 1:
            return "<1s"

        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)

        if hours > 0:
            return f"{hours}h {minutes}m {secs}s"
        elif minutes > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"

    def log_scan_phase(
        self,
        base_path: Path,
        min_confidence: float,
        folders: List[ComputerFolder],
        matches: List[FolderMatch]
    ) -> None:
        """
        Log scan phase results.

        Args:
            base_path: Base directory that was scanned.
            min_confidence: Minimum confidence threshold used.
            folders: List of folders scanned.
            matches: List of match groups found.
        """
        self._write_separator()
        self._write_line("SCAN PHASE")
        self._write_separator()
        self._write_line("")
        self._write_line(f"Base Path: {base_path}")
        self._write_line(f"Minimum Confidence Threshold: {min_confidence}%")
        self._write_line(f"Total folders scanned: {len(folders)}")
        self._write_line(f"Match groups found: {len(matches)}")

        # Count matches above threshold (all matches returned are above threshold)
        matches_above = len(matches)
        self._write_line(f"Match groups above threshold: {matches_above}")
        self._write_line("")

        # Log each match group
        for idx, match in enumerate(matches, start=1):
            reason_text = match.match_reason.value.replace("_", " ").title()
            self._write_line(f"Group {idx}: ({match.confidence:.0f}% - {reason_text})")
            for folder in match.folders:
                self._write_line(f"  - {folder.name}")
            self._write_line("")

    def log_merge_phase_header(self) -> None:
        """
        Write MERGE PHASE section header.

        This method writes the MERGE PHASE section using separator lines
        and a heading, followed by a blank line. It is idempotent and will
        only write the header once per log file.
        """
        if self._merge_phase_started:
            return

        self._merge_phase_started = True
        self._write_separator()
        self._write_line("MERGE PHASE")
        self._write_separator()
        self._write_line("")

    def log_selection(self, selection: MergeSelection, index: int) -> None:
        """
        Log a merge selection.

        Args:
            selection: MergeSelection to log.
            index: Selection index number.
        """
        self._write_line(f"Selection {index}:")
        self._write_line(f"  Confidence: {selection.match_group.confidence:.0f}%")
        self._write_line(f"  Primary: {selection.primary.name}")
        self._write_line("  Merging from:")
        for folder in selection.merge_from:
            self._write_line(f"    - {folder.name}")
        self._write_line("")

    def log_merge_start(self, folder_name: str) -> None:
        """
        Log merge operation start.

        Args:
            folder_name: Name of the primary folder being merged into.
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._write_line(f"[{timestamp}] Starting merge into: {folder_name}")

    def log_merge_progress(
        self,
        source_folder_name: str,
        operation: MergeOperation
    ) -> None:
        """
        Log merge progress for a source folder.

        Args:
            source_folder_name: Name of the source folder being merged.
            operation: MergeOperation with current statistics.
        """
        self._write_line(f"  Merging: {source_folder_name}")
        self._write_line(f"    Files copied: {operation.files_copied}")
        self._write_line(f"    Files skipped (duplicates): {operation.files_skipped}")
        self._write_line(f"    Conflicts resolved: {operation.conflicts_resolved}")
        self._write_line(f"    Empty folders removed: {operation.folders_removed}")

        # Log errors if any
        for error in operation.errors:
            self._write_line(f"    ! Error: {error}")

    def log_merge_complete(self, folder_name: str) -> None:
        """
        Log merge operation completion.

        Args:
            folder_name: Name of the primary folder that was merged into.
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._write_line(f"[{timestamp}] Completed merge into: {folder_name}")
        self._write_line("")

    def log_summary(
        self,
        operations: List[MergeOperation],
        duration: float
    ) -> None:
        """
        Log final summary of all merge operations.

        Args:
            operations: List of completed MergeOperation objects.
            duration: Total workflow duration in seconds.
        """
        self._write_separator()
        self._write_line("SUMMARY")
        self._write_separator()
        self._write_line("")

        # Calculate totals
        total_copied = sum(op.files_copied for op in operations)
        total_skipped = sum(op.files_skipped for op in operations)
        total_conflicts = sum(op.conflicts_resolved for op in operations)
        total_removed = sum(op.folders_removed for op in operations)
        all_errors = [err for op in operations for err in op.errors]

        self._write_line(f"Total merge operations: {len(operations)}")
        self._write_line(f"Files copied: {total_copied:,}")
        self._write_line(f"Files skipped (duplicates): {total_skipped:,}")
        self._write_line(f"Conflicts resolved: {total_conflicts:,}")
        self._write_line(f"Empty folders removed: {total_removed:,}")
        self._write_line(f"Duration: {self._format_duration(duration)}")
        self._write_line("")

        if all_errors:
            self._write_line(f"Errors encountered: {len(all_errors)}")
            for error in all_errors:
                self._write_line(f"  ! {error}")
            self._write_line("")

        self._write_line(f"Log file: {self.log_file_path}")
        self._write_separator()

        # Flush to ensure data is written
        if self._file_handle:
            self._file_handle.flush()

    def log_error(self, error_message: str) -> None:
        """
        Log an error with timestamp.

        Args:
            error_message: Error message to log.
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._write_line(f"[{timestamp}] ERROR: {error_message}")

        # Flush immediately for errors
        if self._file_handle:
            self._file_handle.flush()

    def close(self) -> None:
        """Close the log file."""
        if self._file_handle:
            self._file_handle.flush()
            self._file_handle.close()
            self._file_handle = None

    def __enter__(self) -> 'MergeLogger':
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - ensure log file is closed."""
        self.close()
