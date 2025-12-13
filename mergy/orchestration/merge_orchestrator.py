"""
Merge orchestrator for the Computer Data Organization Tool.

This module contains the MergeOrchestrator class which coordinates the complete
5-phase merge workflow:
1. Scan: Collect folder metadata and find matches
2. Selection: Interactive user selection of merge targets
3. Analysis: Preview merge operations (dry-run)
4. Execution: Perform actual merge operations
5. Summary: Display final results and statistics
"""

from pathlib import Path
from typing import List, Optional, TYPE_CHECKING
from datetime import datetime
import os
import logging
import time

from mergy.models import (
    ComputerFolder, FolderMatch, MergeSelection, FileConflict,
    MergeOperation, MergeSummary
)
from mergy.matching import FolderMatcher
from mergy.scanning import FileHasher, FolderScanner
from mergy.operations import FileOperations
from mergy.ui import MergeTUI

if TYPE_CHECKING:
    from mergy.orchestration.merge_logger import MergeLogger

# Configure module logger
logger = logging.getLogger(__name__)


class MergeOrchestrator:
    """
    Coordinates the complete 5-phase merge workflow.

    Phases:
    1. Scan: Collect folder metadata and find matches
    2. Selection: Interactive user selection of merge targets
    3. Analysis: Preview merge operations (dry-run)
    4. Execution: Perform actual merge operations
    5. Summary: Display final results and statistics
    """

    def __init__(
        self,
        base_path: Path,
        min_confidence: float = 70.0,
        dry_run: bool = False,
        verbose: bool = False,
        logger_instance: Optional['MergeLogger'] = None
    ) -> None:
        """
        Initialize orchestrator with workflow parameters.

        Args:
            base_path: Base directory containing folders to scan.
            min_confidence: Minimum confidence threshold for matches (0-100).
            dry_run: If True, perform analysis without actual file operations.
            verbose: If True, enable verbose output.
            logger_instance: Optional MergeLogger for structured logging.
        """
        self.base_path = Path(base_path).resolve()
        self.min_confidence = min_confidence
        self.dry_run = dry_run
        self.verbose = verbose

        # Initialize component instances
        self.scanner = FolderScanner(self.base_path)
        self.matcher = FolderMatcher(min_confidence)
        self.file_hasher = FileHasher()
        self.file_ops = FileOperations(self.file_hasher, dry_run)
        self.tui = MergeTUI(dry_run)
        self.merge_logger = logger_instance

        # Workflow state
        self.selections: List[MergeSelection] = []
        self.operations: List[MergeOperation] = []
        self.start_time: Optional[float] = None

    def execute_scan_phase(self) -> List[FolderMatch]:
        """
        Phase 1: Scan directories and find matching folder groups.

        Returns:
            List of FolderMatch objects above confidence threshold.
        """
        self.tui.console.print("[bold blue]Phase 1: Scanning folders...[/bold blue]")

        # Scan for folders
        folders = self.scanner.scan()

        # Log scan errors if any
        if self.scanner.errors:
            for error in self.scanner.errors:
                logger.warning(error)
                if self.merge_logger:
                    self.merge_logger.log_error(error)

        # Find matches
        matches = self.matcher.find_matches(folders)

        # Count matches above threshold (already filtered by matcher)
        matches_above_threshold = len(matches)

        # Display scan summary
        self.tui.console.print(
            f"  Scanned [green]{len(folders)}[/green] folders"
        )
        self.tui.console.print(
            f"  Found [yellow]{matches_above_threshold}[/yellow] match groups "
            f"above {self.min_confidence}% confidence"
        )

        # Log to file if logger available
        if self.merge_logger:
            self.merge_logger.log_scan_phase(
                self.base_path, self.min_confidence, folders, matches
            )

        return matches

    def execute_selection_phase(
        self, matches: List[FolderMatch]
    ) -> List[MergeSelection]:
        """
        Phase 2: Interactive selection of folders to merge.

        Args:
            matches: List of FolderMatch objects from scan phase.

        Returns:
            List of confirmed MergeSelection objects.
        """
        self.tui.console.print(
            "\n[bold blue]Phase 2: Select folders to merge[/bold blue]"
        )

        selections: List[MergeSelection] = []
        total_matches = len(matches)

        for idx, match in enumerate(matches, start=1):
            try:
                # Display match group
                self.tui.display_match_group(match, idx, total_matches)

                # Get user action
                action = self.tui.prompt_merge_action()

                if action == "q":
                    self.tui.console.print("[yellow]Quitting selection phase.[/yellow]")
                    break

                if action == "s":
                    if self.verbose:
                        self.tui.console.print("[dim]Skipped.[/dim]")
                    continue

                # action == "m" - proceed with merge selection
                folder_indices = self.tui.prompt_folder_selection(match)
                selected_folders = [match.folders[i] for i in folder_indices]

                primary_idx = self.tui.prompt_primary_selection(selected_folders)
                primary_folder = selected_folders[primary_idx]

                # Create merge-from list (all selected except primary)
                merge_from = [f for i, f in enumerate(selected_folders) if i != primary_idx]

                # Create selection
                selection = MergeSelection(
                    primary=primary_folder,
                    merge_from=merge_from,
                    match_group=match
                )

                # Confirm selection
                if self.tui.confirm_merge(selection):
                    selections.append(selection)

                    # Log selection
                    if self.merge_logger:
                        self.merge_logger.log_merge_phase_header()
                        self.merge_logger.log_selection(selection, len(selections))

                    if self.verbose:
                        self.tui.console.print(
                            "[green]Selection confirmed.[/green]"
                        )
                else:
                    if self.verbose:
                        self.tui.console.print("[yellow]Selection cancelled.[/yellow]")

            except KeyboardInterrupt:
                self.tui.console.print(
                    "\n[yellow]Interrupted. Returning current selections.[/yellow]"
                )
                break

        self.selections = selections
        return selections

    def execute_analysis_phase(
        self, selection: MergeSelection
    ) -> tuple[MergeOperation, List[FileConflict]]:
        """
        Phase 3: Analyze merge operation in dry-run mode.

        Args:
            selection: MergeSelection to analyze.

        Returns:
            Tuple of (MergeOperation with analysis stats, list of FileConflict).
        """
        # Create separate FileHasher for analysis to avoid mixing with execution cache
        analysis_hasher = FileHasher()

        # Create temporary FileOperations in dry-run mode for analysis
        analysis_ops = FileOperations(analysis_hasher, dry_run=True)

        # Create operation for analysis
        operation = MergeOperation(
            selection=selection,
            dry_run=True,
            timestamp=datetime.now()
        )

        conflicts: List[FileConflict] = []
        primary_folder = selection.primary.path

        # Analyze each merge-from folder
        for source_folder in selection.merge_from:
            self._analyze_folder(
                source_folder.path,
                primary_folder,
                operation,
                conflicts,
                analysis_hasher
            )

        # Count empty directories that would be removed
        for source_folder in selection.merge_from:
            count = analysis_ops._count_empty_dirs(source_folder.path)
            operation.folders_removed += count

        # Display analysis
        self.tui.display_analysis_summary(operation, conflicts)

        return operation, conflicts

    def _analyze_folder(
        self,
        source_folder: Path,
        primary_folder: Path,
        operation: MergeOperation,
        conflicts: List[FileConflict],
        file_hasher: FileHasher
    ) -> None:
        """
        Analyze files in a source folder for merge preview.

        Args:
            source_folder: Source folder to analyze.
            primary_folder: Destination primary folder.
            operation: MergeOperation to update with stats.
            conflicts: List to append detected conflicts.
            file_hasher: FileHasher instance to use for hash calculations.
        """
        for root, dirs, files in os.walk(source_folder, followlinks=True):
            root_path = Path(root)
            dirs[:] = [d for d in dirs if d != FileOperations.MERGED_DIR_NAME]

            for filename in files:
                source_file = root_path / filename
                relative_path = source_file.relative_to(source_folder)
                dest_file = primary_folder / relative_path

                try:
                    if not dest_file.exists():
                        operation.files_copied += 1
                    else:
                        # Compare hashes
                        source_hash = file_hasher.get_hash(source_file)
                        dest_hash = file_hasher.get_hash(dest_file)

                        if source_hash and dest_hash:
                            if source_hash == dest_hash:
                                operation.files_skipped += 1
                            else:
                                operation.conflicts_resolved += 1
                                # Create conflict record for display
                                source_stat = source_file.stat()
                                dest_stat = dest_file.stat()
                                conflict = FileConflict(
                                    relative_path=relative_path,
                                    primary_file=dest_file,
                                    conflicting_file=source_file,
                                    primary_hash=dest_hash,
                                    conflict_hash=source_hash,
                                    primary_ctime=datetime.fromtimestamp(dest_stat.st_ctime),
                                    conflict_ctime=datetime.fromtimestamp(source_stat.st_ctime)
                                )
                                conflicts.append(conflict)
                except (PermissionError, OSError) as e:
                    operation.errors.append(f"Analysis error: {source_file} - {e}")

    def execute_execution_phase(
        self, selections: List[MergeSelection]
    ) -> List[MergeOperation]:
        """
        Phase 4: Execute merge operations.

        Args:
            selections: List of MergeSelection objects to execute.

        Returns:
            List of completed MergeOperation objects.
        """
        self.tui.console.print(
            "\n[bold blue]Phase 4: Executing merge operations...[/bold blue]"
        )

        operations: List[MergeOperation] = []

        for idx, selection in enumerate(selections, start=1):
            folder_name = selection.primary.name

            try:
                # Log merge start
                if self.merge_logger:
                    self.merge_logger.log_merge_phase_header()
                    self.merge_logger.log_merge_start(folder_name)

                # Calculate total files for progress
                total_files = sum(f.file_count for f in selection.merge_from)

                # Execute merge with progress bar
                with self.tui.show_progress_bar(f"Merging into {folder_name}") as progress:
                    task = progress.add_task(
                        f"Merging into {folder_name}",
                        total=total_files if total_files > 0 else 1
                    )

                    # Execute the actual merge
                    operation = self.file_ops.merge_folders(selection)
                    operations.append(operation)

                    # Update progress to complete
                    progress.update(task, completed=total_files if total_files > 0 else 1)

                # Log merge progress and completion
                if self.merge_logger:
                    for source_folder in selection.merge_from:
                        self.merge_logger.log_merge_progress(
                            source_folder.name, operation
                        )
                    self.merge_logger.log_merge_complete(folder_name)

                if self.verbose:
                    self.tui.console.print(
                        f"  [green]✓[/green] Merged into {folder_name}"
                    )

            except OSError as e:
                # Critical error (disk full) - abort remaining merges
                if "No space left on device" in str(e) or getattr(e, 'errno', None) == 28:
                    error_msg = f"Disk full - aborting merge operations: {e}"
                    self.tui.console.print(f"[bold red]{error_msg}[/bold red]")
                    if self.merge_logger:
                        self.merge_logger.log_error(error_msg)
                    break
                raise

            except KeyboardInterrupt:
                self.tui.console.print(
                    "\n[yellow]Interrupted. Stopping merge operations.[/yellow]"
                )
                break

        self.operations = operations
        return operations

    def execute_summary_phase(
        self, operations: List[MergeOperation]
    ) -> MergeSummary:
        """
        Phase 5: Display and log final summary.

        Args:
            operations: List of completed MergeOperation objects.

        Returns:
            MergeSummary with summary statistics.
        """
        self.tui.console.print("\n[bold blue]Phase 5: Summary[/bold blue]")

        # Calculate duration
        duration = time.time() - self.start_time if self.start_time else 0.0

        # Calculate totals
        summary = MergeSummary(
            total_operations=len(operations),
            files_copied=sum(op.files_copied for op in operations),
            files_skipped=sum(op.files_skipped for op in operations),
            conflicts_resolved=sum(op.conflicts_resolved for op in operations),
            folders_removed=sum(op.folders_removed for op in operations),
            errors=[err for op in operations for err in op.errors],
            duration=duration
        )

        # Display TUI summary
        self.tui.display_summary(operations, duration)

        # Log to file
        if self.merge_logger:
            self.merge_logger.log_summary(operations, duration)

        return summary

    def run_scan_workflow(self) -> List[FolderMatch]:
        """
        Run scan-only workflow (no merge).

        Returns:
            List of FolderMatch objects found.
        """
        self.start_time = time.time()

        try:
            matches = self.execute_scan_phase()
            return matches
        except KeyboardInterrupt:
            self.tui.console.print("\n[yellow]Scan interrupted.[/yellow]")
            return []

    def run_merge_workflow(self) -> MergeSummary:
        """
        Run complete interactive merge workflow.

        Returns:
            MergeSummary with summary statistics.
        """
        self.start_time = time.time()

        try:
            # Phase 1: Scan
            matches = self.execute_scan_phase()

            if not matches:
                self.tui.console.print(
                    "[yellow]No matching folders found above confidence threshold.[/yellow]"
                )
                duration = time.time() - self.start_time if self.start_time else 0.0
                return MergeSummary(duration=duration)

            # Phase 2: Selection
            selections = self.execute_selection_phase(matches)

            if not selections:
                self.tui.console.print(
                    "[yellow]No folders selected for merging.[/yellow]"
                )
                duration = time.time() - self.start_time if self.start_time else 0.0
                return MergeSummary(duration=duration)

            # Phase 3: Analysis (for each selection)
            self.tui.console.print(
                "\n[bold blue]Phase 3: Analyzing merge operations...[/bold blue]"
            )
            for selection in selections:
                self.tui.console.print(
                    f"\n[bold]Analyzing merge into: {selection.primary.name}[/bold]"
                )
                self.execute_analysis_phase(selection)

            # Phase 4: Execution
            operations = self.execute_execution_phase(selections)

            # Phase 5: Summary
            summary = self.execute_summary_phase(operations)

            return summary

        except KeyboardInterrupt:
            self.tui.console.print(
                "\n[yellow]Workflow interrupted by user.[/yellow]"
            )
            duration = time.time() - self.start_time if self.start_time else 0.0
            return MergeSummary(
                total_operations=len(self.operations),
                files_copied=sum(op.files_copied for op in self.operations),
                files_skipped=sum(op.files_skipped for op in self.operations),
                conflicts_resolved=sum(op.conflicts_resolved for op in self.operations),
                folders_removed=sum(op.folders_removed for op in self.operations),
                errors=[err for op in self.operations for err in op.errors],
                duration=duration,
                interrupted=True
            )
