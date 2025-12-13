"""MergeOrchestrator for coordinating folder scanning and merging workflows.

This module provides the MergeOrchestrator class that orchestrates the complete
scan and merge workflows per AGENTS.md specification. It coordinates FolderScanner,
FolderMatcher, MergeTUI, FileOperations, and MergeLogger to implement both
read-only scanning and interactive merging workflows.

Example:
    from mergy.orchestration import MergeOrchestrator
    from pathlib import Path

    orchestrator = MergeOrchestrator(
        base_path=Path("/data/computers"),
        min_confidence=0.7,
        dry_run=False
    )

    # Scan only
    matches = orchestrator.scan()

    # Interactive merge
    summary = orchestrator.merge()
"""

import errno
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from mergy.matching import FolderMatcher
from mergy.models import (
    ComputerFolder,
    FileConflict,
    FolderMatch,
    MergeOperation,
    MergeSelection,
    MergeSummary,
)
from mergy.operations import FileOperations
from mergy.orchestration.merge_logger import MergeLogger
from mergy.scanning import FileHasher, FolderScanner
from mergy.ui import MergeTUI


class MergeOrchestrator:
    """Orchestrates folder scanning and merging workflows.

    Coordinates FolderScanner, FolderMatcher, MergeTUI, FileOperations,
    and MergeLogger to implement complete scan and merge workflows per
    AGENTS.md specification.

    The orchestrator exposes two primary methods:
    - scan(): Read-only analysis that displays results and logs
    - merge(): Interactive merging with selection, execution, and summary

    Both workflows share a common scan phase, then diverge—scan displays
    results and logs, while merge adds interactive selection, execution
    with progress tracking, and summary aggregation.

    Attributes:
        base_path: Path to the base directory containing folders to scan.
        min_confidence: Minimum confidence threshold for folder matching.
        log_file_path: Optional path for the log file.
        dry_run: Whether to simulate operations without making changes.
        verbose: Whether to display verbose output.

    Example:
        orchestrator = MergeOrchestrator(
            base_path=Path("/data/computers"),
            min_confidence=0.7,
            dry_run=False
        )

        # Scan only
        matches = orchestrator.scan()

        # Interactive merge
        summary = orchestrator.merge()
    """

    def __init__(
        self,
        base_path: Path,
        min_confidence: float = 0.7,
        log_file_path: Optional[Path] = None,
        dry_run: bool = False,
        verbose: bool = False,
    ) -> None:
        """Initialize the MergeOrchestrator.

        Args:
            base_path: Path to the base directory containing folders to scan.
            min_confidence: Minimum confidence threshold for folder matching
                (0.0 to 1.0). Defaults to 0.7 (70%).
            log_file_path: Optional path for the log file. If not provided,
                a timestamped filename will be generated.
            dry_run: If True, simulate operations without making changes.
                Defaults to False.
            verbose: If True, display additional details during execution.
                Defaults to False.

        Raises:
            ValueError: If base_path does not exist or is not a directory.
            ValueError: If min_confidence is not between 0.0 and 1.0.
        """
        # Validate base_path exists and is a directory (critical error per spec 8.1)
        resolved_path = base_path.resolve()
        if not resolved_path.exists():
            raise ValueError(f"Base path does not exist: {base_path}")
        if not resolved_path.is_dir():
            raise ValueError(f"Base path is not a directory: {base_path}")

        # Validate min_confidence
        if not 0.0 <= min_confidence <= 1.0:
            raise ValueError(
                f"min_confidence must be between 0.0 and 1.0, got {min_confidence}"
            )

        self.base_path = resolved_path
        self.min_confidence = min_confidence
        self.log_file_path = log_file_path
        self.dry_run = dry_run
        self.verbose = verbose

        # Initialize component instances
        self._scanner = FolderScanner()
        self._matcher = FolderMatcher(min_confidence=min_confidence)
        self._tui = MergeTUI()

        # Error tracking list for orchestrator-level errors
        self._errors: List[str] = []

    def scan(self) -> List[FolderMatch]:
        """Execute a read-only scan workflow.

        Scans the base path for folders, identifies matches, displays results
        via TUI, and logs the scan phase to a log file.

        Returns:
            List of FolderMatch objects found during scanning.

        Raises:
            ValueError: If the base path is invalid (from constructor).
        """
        # Execute scan phase
        folders, matches = self._execute_scan_phase()

        # Display scan summary via TUI
        self._tui.display_scan_summary(
            matches=matches,
            total_scanned=len(folders),
            threshold=self.min_confidence,
        )

        # Log scan results (scan is always read-only, so dry_run=False for logging)
        try:
            with MergeLogger(
                log_file_path=self.log_file_path,
                dry_run=False,
                base_path=self.base_path,
            ) as logger:
                logger.log_header()
                logger.log_scan_phase(
                    base_path=self.base_path,
                    min_confidence=self.min_confidence,
                    total_folders=len(folders),
                    match_groups=matches,
                    threshold_filtered_count=len(matches),
                )

                if self.verbose:
                    self._tui.console.print(
                        f"[dim]Log file: {logger.get_log_path()}[/dim]"
                    )
        except OSError as e:
            # Handle logger initialization failure (non-critical - log to stderr)
            print(f"Warning: Could not create log file: {e}", file=sys.stderr)

        # Show scanner errors if verbose
        if self.verbose and self._scanner.get_errors():
            self._tui.console.print("[yellow]Scanner warnings:[/yellow]")
            for error in self._scanner.get_errors():
                self._tui.console.print(f"  [dim]- {error}[/dim]")

        return matches

    def merge(self) -> MergeSummary:
        """Execute an interactive merge workflow.

        Implements the 5-phase workflow from spec section 4.2:
        1. Scan - Collect folders and find matches
        2. Interactive Selection - User reviews and selects matches to merge
        3. Analysis - Preview operations (verbose mode)
        4. Execution - Execute merge operations with progress tracking
        5. Summary - Aggregate statistics and display/log results

        Returns:
            MergeSummary with aggregated statistics across all operations.

        Raises:
            ValueError: If the base path is invalid (from constructor).
        """
        start_time = time.time()
        self._errors.clear()

        # Phase 1: Scan
        folders, matches = self._execute_scan_phase()

        # Display scan summary
        self._tui.display_scan_summary(
            matches=matches,
            total_scanned=len(folders),
            threshold=self.min_confidence,
        )

        # Handle no matches case
        if not matches:
            return self._create_empty_summary(time.time() - start_time)

        # Phase 2: Interactive Selection
        try:
            selections = self._tui.review_match_groups(matches)
        except KeyboardInterrupt:
            # User cancelled with Ctrl+C - return early summary
            self._tui.console.print("\n[yellow]Merge cancelled by user.[/yellow]")
            return self._create_empty_summary(time.time() - start_time)

        # Handle user skipping all or quitting early
        if not selections:
            if self.verbose:
                self._tui.console.print("[dim]No selections made.[/dim]")
            return self._create_empty_summary(time.time() - start_time)

        # Phase 3 & 4: Analysis and Execution (with optional logging)
        # Try to create logger; if it fails, proceed without logging
        logger: Optional[MergeLogger] = None
        try:
            logger = MergeLogger(
                log_file_path=self.log_file_path,
                dry_run=self.dry_run,
                base_path=self.base_path,
            )
        except OSError as e:
            print(f"Warning: Could not create log file: {e}", file=sys.stderr)

        if logger is not None:
            with logger:
                # Log header and scan phase
                logger.log_header()
                logger.log_scan_phase(
                    base_path=self.base_path,
                    min_confidence=self.min_confidence,
                    total_folders=len(folders),
                    match_groups=matches,
                    threshold_filtered_count=len(matches),
                )

                # Execute merge operations
                operations = self._execute_merge_operations(selections, logger)

                # Phase 5: Summary
                duration = time.time() - start_time
                all_errors = self._errors.copy()
                for op in operations:
                    all_errors.extend(op.errors)

                summary = self._aggregate_summary(operations, duration, all_errors)

                # Display merge summary via TUI
                self._tui.display_merge_summary(summary, self.dry_run)

                # Log summary
                logger.log_summary(summary)
                if self.verbose:
                    self._tui.console.print(
                        f"[dim]Log file: {logger.get_log_path()}[/dim]"
                    )

                return summary
        else:
            # Execute merge operations without logging
            operations = self._execute_merge_operations(selections, None)

            # Phase 5: Summary
            duration = time.time() - start_time
            all_errors = self._errors.copy()
            for op in operations:
                all_errors.extend(op.errors)

            summary = self._aggregate_summary(operations, duration, all_errors)

            # Display merge summary via TUI
            self._tui.display_merge_summary(summary, self.dry_run)

            return summary

    def _execute_scan_phase(self) -> Tuple[List[ComputerFolder], List[FolderMatch]]:
        """Execute the scan phase of the workflow.

        Scans immediate subdirectories of the base path and identifies
        matching folder groups.

        Returns:
            Tuple of (all_folders, match_groups) for use by both scan and
            merge workflows.
        """
        # Clear previous scanner errors
        self._scanner.clear_errors()

        # Scan immediate subdirectories
        folders = self._scanner.scan_immediate_subdirectories(self.base_path)

        # Collect scanner errors
        scanner_errors = self._scanner.get_errors()
        self._errors.extend(scanner_errors)

        if self.verbose and scanner_errors:
            self._tui.console.print(f"[dim]Scanner encountered {len(scanner_errors)} warnings[/dim]")

        # Find matches using the matcher
        matches = self._matcher.find_matches(folders)

        return folders, matches

    def _execute_merge_operations(
        self,
        selections: List[MergeSelection],
        logger: Optional[MergeLogger],
    ) -> List[MergeOperation]:
        """Execute merge operations for all selections.

        Args:
            selections: List of MergeSelection objects from user review.
            logger: Optional MergeLogger for logging operations.

        Returns:
            List of completed MergeOperation objects.
        """
        operations: List[MergeOperation] = []

        for selection in selections:
            # Log selection
            if logger is not None:
                logger.log_merge_selection(selection)

            # Count total files for progress tracking
            total_files = self._count_files_in_selection(selection)

            if self.verbose:
                self._tui.console.print(
                    f"[dim]Processing {selection.primary.name}: {total_files} files[/dim]"
                )

            # Track conflicts for logging (only in verbose mode to avoid duplicate hashing)
            conflicts: List[FileConflict] = []
            if self.verbose:
                conflicts = self._track_conflicts_for_operation(selection)

            # Create progress callback
            progress, callback = self._tui.create_progress_callback(
                folder_name=selection.primary.name,
                total_files=total_files,
            )

            # Create FileOperations with progress callback
            file_ops = FileOperations(
                progress_callback=self._create_progress_wrapper(callback)
            )

            try:
                # Execute merge with progress tracking
                with progress:
                    operation = file_ops.merge_folders(selection, self.dry_run)

                operations.append(operation)

                # Log operation with conflicts
                if logger is not None:
                    logger.log_merge_operation(operation, conflicts)

            except OSError as e:
                if e.errno == errno.ENOSPC:
                    # Disk full - critical error, abort remaining operations
                    error_msg = f"Disk full during merge of {selection.primary.name}"
                    self._errors.append(error_msg)
                    self._tui.console.print(f"[red]Critical error: {error_msg}[/red]")
                    break
                else:
                    # Other OS error - non-critical, log and continue
                    error_msg = f"Error merging {selection.primary.name}: {e}"
                    self._errors.append(error_msg)
                    if self.verbose:
                        self._tui.console.print(f"[yellow]Warning: {error_msg}[/yellow]")

        return operations

    def _track_conflicts_for_operation(
        self, selection: MergeSelection
    ) -> List[FileConflict]:
        """Track conflicts for an operation before execution.

        Walks source folders to identify files that would conflict with
        the primary folder and builds FileConflict objects for logging.

        Args:
            selection: The MergeSelection to analyze.

        Returns:
            List of FileConflict objects for files with different hashes.
        """
        conflicts: List[FileConflict] = []
        hasher = FileHasher()
        primary_folder = selection.primary.path

        for source_folder in selection.merge_from:
            try:
                for source_file in self._walk_files_recursive(source_folder.path):
                    # Get relative path from source folder
                    rel_path = source_file.relative_to(source_folder.path)
                    primary_file = primary_folder / rel_path

                    # Check if file exists in primary
                    if not primary_file.exists():
                        continue

                    # Compare hashes
                    primary_hash = hasher.hash_file(primary_file)
                    source_hash = hasher.hash_file(source_file)

                    if primary_hash is None or source_hash is None:
                        continue

                    # Same hash = duplicate, not conflict
                    if primary_hash == source_hash:
                        continue

                    # Different hashes - this is a conflict
                    try:
                        primary_stat = primary_file.stat()
                        source_stat = source_file.stat()

                        conflict = FileConflict(
                            relative_path=rel_path,
                            primary_file=primary_file,
                            conflicting_file=source_file,
                            primary_hash=primary_hash,
                            conflict_hash=source_hash,
                            primary_ctime=datetime.fromtimestamp(primary_stat.st_ctime),
                            conflict_ctime=datetime.fromtimestamp(source_stat.st_ctime),
                        )
                        conflicts.append(conflict)
                    except OSError:
                        # Can't stat files - skip this conflict
                        continue

            except OSError as e:
                self._errors.append(f"Error scanning {source_folder.path}: {e}")

        return conflicts

    def _count_files_in_selection(self, selection: MergeSelection) -> int:
        """Count total files in source folders of a selection.

        Args:
            selection: The MergeSelection to count files for.

        Returns:
            Total number of files across all source folders.
        """
        total = 0
        for source_folder in selection.merge_from:
            for _ in self._walk_files_recursive(source_folder.path):
                total += 1
        return total

    def _walk_files_recursive(self, folder: Path):
        """Walk a folder and yield all files.

        Skips .merged/ directories during traversal.

        Args:
            folder: Root folder to walk.

        Yields:
            Path to each file in the folder tree.
        """
        import os

        try:
            for dirpath, dirnames, filenames in os.walk(folder):
                # Skip .merged directories
                if ".merged" in dirnames:
                    dirnames.remove(".merged")

                for filename in filenames:
                    yield Path(dirpath) / filename
        except OSError:
            pass

    def _create_progress_wrapper(
        self, callback: Callable[[int], None]
    ) -> Callable[[int, int, str], None]:
        """Create a progress callback wrapper for FileOperations.

        FileOperations expects (current_index, total_files, current_file_name)
        but MergeTUI callback only needs (completed).

        Args:
            callback: MergeTUI progress callback that takes completed count.

        Returns:
            Wrapped callback compatible with FileOperations.
        """
        def wrapper(current_index: int, total_files: int, current_file: str) -> None:
            callback(current_index + 1)

        return wrapper

    def _aggregate_summary(
        self,
        operations: List[MergeOperation],
        duration: float,
        all_errors: List[str],
    ) -> MergeSummary:
        """Aggregate statistics across all merge operations.

        Args:
            operations: List of completed MergeOperation objects.
            duration: Total duration of the merge workflow in seconds.
            all_errors: Aggregated list of all errors encountered.

        Returns:
            MergeSummary dataclass with totals and duration.
        """
        total_files_copied = sum(op.files_copied for op in operations)
        total_files_skipped = sum(op.files_skipped for op in operations)
        total_conflicts_resolved = sum(op.conflicts_resolved for op in operations)
        total_folders_removed = sum(op.folders_removed for op in operations)

        return MergeSummary(
            total_operations=len(operations),
            total_files_copied=total_files_copied,
            total_files_skipped=total_files_skipped,
            total_conflicts_resolved=total_conflicts_resolved,
            total_folders_removed=total_folders_removed,
            duration_seconds=duration,
            errors=all_errors,
        )

    def _create_empty_summary(self, duration: float) -> MergeSummary:
        """Create an empty summary when no operations were performed.

        Args:
            duration: Duration of the workflow in seconds.

        Returns:
            MergeSummary with zero values.
        """
        return MergeSummary(
            total_operations=0,
            total_files_copied=0,
            total_files_skipped=0,
            total_conflicts_resolved=0,
            total_folders_removed=0,
            duration_seconds=duration,
            errors=self._errors.copy(),
        )
