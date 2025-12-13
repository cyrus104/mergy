"""Terminal User Interface for Mergy folder merging.

This module provides the MergeTUI class, a Rich-based interactive TUI
for reviewing folder matches and managing merge operations.

Example:
    from mergy.ui import MergeTUI
    from mergy.models import FolderMatch, MergeSummary

    tui = MergeTUI()
    tui.display_scan_summary(matches, total_scanned=100, threshold=0.7)
    selections = tui.review_match_groups(matches)
    tui.display_merge_summary(summary, dry_run=False)
"""

from typing import Callable, List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.prompt import Confirm, Prompt
from rich.table import Table

from mergy.models import ComputerFolder, FolderMatch, MergeSelection, MergeSummary


class MergeTUI:
    """Rich-based Terminal User Interface for folder merge operations.

    Provides interactive display and selection methods for the merge workflow:
    - Display scan results in formatted tables
    - Interactive match group review with merge/skip/quit actions
    - Progress tracking for file operations
    - Summary display with statistics and errors

    Args:
        console: Optional Rich Console instance for output. If None, creates
            a new Console. Pass a custom Console for testing (e.g., with
            StringIO file for output capture).

    Attributes:
        console: The Rich Console instance used for all output.
    """

    def __init__(self, console: Optional[Console] = None) -> None:
        """Initialize MergeTUI with optional custom console.

        Args:
            console: Optional Rich Console for output. Defaults to new Console().
        """
        self.console = console or Console()
        self._match_group_count: int = 0

    def display_scan_summary(
        self, matches: List[FolderMatch], total_scanned: int, threshold: float
    ) -> None:
        """Display read-only scan results in a formatted table.

        Shows a header panel with statistics and a table of all match groups
        with confidence levels, match types, and folder information.

        Args:
            matches: List of FolderMatch objects found during scanning.
            total_scanned: Total number of folders scanned.
            threshold: Confidence threshold used for matching (0.0-1.0).
        """
        threshold_pct = int(threshold * 100)
        header_text = (
            f"Folders scanned: {total_scanned:,}\n"
            f"Match groups found: {len(matches)}\n"
            f"Confidence threshold: {threshold_pct}%"
        )
        header_panel = Panel(header_text, title="Scan Results", border_style="blue")
        self.console.print(header_panel)

        if not matches:
            self.console.print("[yellow]No match groups found.[/yellow]")
            return

        table = Table(title="Match Groups")
        table.add_column("Group #", justify="right", style="cyan", no_wrap=True)
        table.add_column("Confidence", justify="center")
        table.add_column("Match Type", style="magenta")
        table.add_column("Folders", style="white")

        for idx, match in enumerate(matches, start=1):
            confidence_pct = int(match.confidence * 100)
            confidence_str = self._format_confidence(confidence_pct)
            match_type = match.match_reason.value
            folder_names = "\n".join(
                self._truncate_name(f.name, max_length=50) for f in match.folders
            )
            table.add_row(str(idx), confidence_str, match_type, folder_names)

        self.console.print(table)

    def review_match_groups(self, matches: List[FolderMatch]) -> List[MergeSelection]:
        """Interactive workflow for reviewing and selecting match groups to merge.

        Displays each match group and prompts for user action (merge/skip/quit).
        For merge actions, guides through folder selection, primary selection,
        and confirmation.

        Args:
            matches: List of FolderMatch objects to review.

        Returns:
            List of MergeSelection objects for matches where user chose to merge
            and confirmed the selection. Returns empty list if user quits or
            skips all groups.

        Raises:
            KeyboardInterrupt is caught internally and treated as quit.
        """
        if not matches:
            return []

        selections: List[MergeSelection] = []
        total = len(matches)

        completed_count = 0
        review_cancelled = False

        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=self.console,
        ) as progress:
            task = progress.add_task(f"Reviewing match groups: 0/{total}", total=total)

            for idx, match in enumerate(matches, start=1):
                progress.update(
                    task,
                    completed=idx - 1,
                    description=f"Reviewing match groups: {idx}/{total}",
                )

                try:
                    self._display_match_group(match, idx)

                    action = self._prompt_action()

                    if action == "q":
                        # User quit - progress reflects last completed group
                        completed_count = idx - 1
                        progress.update(
                            task,
                            completed=completed_count,
                            description=f"Review cancelled: {completed_count}/{total}",
                        )
                        review_cancelled = True
                        break

                    if action == "s":
                        completed_count = idx
                        continue

                    if action == "m":
                        selection = self._process_merge_action(match)
                        if selection:
                            selections.append(selection)
                        completed_count = idx

                except KeyboardInterrupt:
                    self.console.print(
                        "\n[yellow]Operation cancelled by user.[/yellow]"
                    )
                    # Keyboard interrupt - progress reflects last completed group
                    completed_count = idx - 1
                    progress.update(
                        task,
                        completed=completed_count,
                        description=f"Review interrupted: {completed_count}/{total}",
                    )
                    review_cancelled = True
                    break
            else:
                # Loop completed without break - all groups reviewed
                completed_count = total

            # Only set to 100% if all groups were reviewed
            if not review_cancelled:
                progress.update(task, completed=total)

        return selections

    def display_merge_summary(self, summary: MergeSummary, dry_run: bool) -> None:
        """Display final statistics after all merges complete.

        Shows a summary panel with operation statistics and optionally
        displays errors if any occurred.

        Args:
            summary: MergeSummary with aggregated statistics.
            dry_run: If True, displays "[DRY RUN]" indicator.
        """
        title = "Merge Summary"
        if dry_run:
            title += " [yellow][DRY RUN][/yellow]"

        header_panel = Panel(title, border_style="green" if not dry_run else "yellow")
        self.console.print(header_panel)

        table = Table(show_header=True, header_style="bold")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right")

        table.add_row("Total operations", f"{summary.total_operations:,}")
        table.add_row("Files copied", f"{summary.total_files_copied:,}")
        table.add_row("Files skipped (duplicates)", f"{summary.total_files_skipped:,}")
        table.add_row("Conflicts resolved", f"{summary.total_conflicts_resolved:,}")
        table.add_row("Folders removed", f"{summary.total_folders_removed:,}")
        table.add_row("Duration", self._format_duration(summary.duration_seconds))

        self.console.print(table)

        if summary.errors:
            self._display_errors(summary.errors)

    def create_progress_callback(
        self, folder_name: str, total_files: int
    ) -> tuple[Progress, Callable[[int], None]]:
        """Create a progress bar and callback function for file operation tracking.

        This method returns a tuple of (Progress, callback) to give the caller
        full control over the progress bar lifecycle. The caller is responsible
        for using the Progress instance as a context manager.

        Args:
            folder_name: Name of the folder being merged (for display).
            total_files: Total number of files to process.

        Returns:
            tuple[Progress, Callable[[int], None]]: A tuple containing:
                - Progress: Rich Progress instance that MUST be used as a context
                  manager (with statement) to properly render and clean up the
                  progress bar.
                - callback: A function that accepts the number of completed files
                  (int) and updates the progress bar. Call this after each file
                  is processed.

        Note:
            The MergeOrchestrator (or other caller) must wrap file operations
            with `with progress:` to ensure the progress bar displays correctly
            and cleans up properly on completion or error.

        Example:
            progress, callback = tui.create_progress_callback("my-folder", 100)
            with progress:
                for i, file in enumerate(files):
                    process_file(file)
                    callback(i + 1)
        """
        progress = Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=self.console,
        )
        task_id = progress.add_task(f"Merging {folder_name}...", total=total_files)

        def callback(completed: int) -> None:
            progress.update(task_id, completed=completed)

        return progress, callback

    def _display_match_group(self, match: FolderMatch, group_number: int) -> None:
        """Display detailed folder information for a single match group.

        Args:
            match: The FolderMatch to display.
            group_number: 1-based group number for display.
        """
        confidence_pct = int(match.confidence * 100)
        title = (
            f"Match Group {group_number} - "
            f"{confidence_pct}% confidence ({match.match_reason.value})"
        )

        table = Table(show_header=True, header_style="bold")
        table.add_column("#", justify="right", style="cyan", width=3)
        table.add_column("Folder Name", style="white")
        table.add_column("Files", justify="right")
        table.add_column("Size", justify="right")
        table.add_column("Date Range", style="dim")

        long_names: List[str] = []

        for idx, folder in enumerate(match.folders, start=1):
            display_name = self._truncate_name(folder.name, max_length=60)
            if len(folder.name) > 60:
                long_names.append(f"  [{idx}] {folder.name}")

            files_str = f"{folder.file_count:,}"
            size_str = self._format_size(folder.total_size)
            date_range = (
                f"{folder.oldest_file_date.strftime('%Y-%m-%d')} to "
                f"{folder.newest_file_date.strftime('%Y-%m-%d')}"
            )

            table.add_row(str(idx), display_name, files_str, size_str, date_range)

        if long_names:
            table.caption = "Full paths:\n" + "\n".join(long_names)

        panel = Panel(table, title=title, border_style="blue")
        self.console.print(panel)

    def _prompt_action(self) -> str:
        """Prompt user for action on current match group.

        Returns:
            One of 'm' (merge), 's' (skip), or 'q' (quit).
        """
        while True:
            try:
                action = Prompt.ask(
                    "(m)erge, (s)kip, (q)uit",
                    choices=["m", "s", "q"],
                    default="s",
                )
                return action
            except ValueError:
                self.console.print(
                    "[red]Invalid input. Please enter 'm', 's', or 'q'.[/red]"
                )

    def _process_merge_action(self, match: FolderMatch) -> Optional[MergeSelection]:
        """Process a merge action for a match group.

        Args:
            match: The FolderMatch to process.

        Returns:
            MergeSelection if user confirms merge, None otherwise.
        """
        if len(match.folders) < 2:
            self.console.print(
                "[yellow]Cannot merge: need at least 2 folders.[/yellow]"
            )
            return None

        selected_folders = self._select_folders_to_merge(match)
        if not selected_folders or len(selected_folders) < 2:
            self.console.print(
                "[yellow]Need at least 2 folders to merge. Skipping.[/yellow]"
            )
            return None

        primary = self._select_primary_folder(selected_folders)
        merge_from = [f for f in selected_folders if f != primary]

        if self._confirm_merge(primary, merge_from):
            return MergeSelection(
                primary=primary,
                merge_from=merge_from,
                match_group=match,
            )

        return None

    def _select_folders_to_merge(self, match: FolderMatch) -> List[ComputerFolder]:
        """Prompt user to select which folders to merge.

        Args:
            match: The FolderMatch containing available folders.

        Returns:
            List of selected ComputerFolder objects.
        """
        folder_count = len(match.folders)

        while True:
            try:
                selection = Prompt.ask(
                    f"Select folders to merge (e.g., '1 2 3' or 'all')",
                    default="all" if folder_count == 2 else "",
                )

                selection = selection.strip().lower()

                if selection == "all":
                    return list(match.folders)

                if not selection:
                    if folder_count == 2:
                        return list(match.folders)
                    self.console.print(
                        f"[red]Please enter folder numbers (1-{folder_count}) "
                        f"or 'all'.[/red]"
                    )
                    continue

                indices = []
                for part in selection.split():
                    try:
                        idx = int(part)
                        if idx < 1 or idx > folder_count:
                            raise ValueError(f"Index {idx} out of range")
                        indices.append(idx - 1)
                    except ValueError:
                        self.console.print(
                            f"[red]Invalid selection '{part}'. Please enter numbers "
                            f"(1-{folder_count}) or 'all'.[/red]"
                        )
                        break
                else:
                    return [match.folders[i] for i in indices]

            except KeyboardInterrupt:
                raise

    def _select_primary_folder(self, folders: List[ComputerFolder]) -> ComputerFolder:
        """Prompt user to select the primary (destination) folder.

        Args:
            folders: List of folders to choose from.

        Returns:
            The selected primary ComputerFolder.
        """
        largest_idx = 0
        largest_size = 0
        for idx, folder in enumerate(folders):
            if folder.total_size > largest_size:
                largest_size = folder.total_size
                largest_idx = idx

        self.console.print("\nSelect primary folder (destination):")
        for idx, folder in enumerate(folders, start=1):
            suffix = " [recommended]" if idx - 1 == largest_idx else ""
            self.console.print(f"  {idx}. {folder.name}{suffix}")

        choices = [str(i) for i in range(1, len(folders) + 1)]
        default = str(largest_idx + 1)

        selection = Prompt.ask(
            "Primary folder",
            choices=choices,
            default=default,
        )

        return folders[int(selection) - 1]

    def _confirm_merge(
        self, primary: ComputerFolder, merge_from: List[ComputerFolder]
    ) -> bool:
        """Display merge summary and prompt for confirmation.

        Args:
            primary: The primary (destination) folder.
            merge_from: List of folders to merge from.

        Returns:
            True if user confirms, False otherwise.
        """
        merge_from_names = "\n".join(f"  - {f.name}" for f in merge_from)
        summary_text = (
            f"[bold green]Primary folder:[/bold green] {primary.name}\n\n"
            f"[bold]Merging from:[/bold]\n{merge_from_names}\n\n"
            f"[yellow]This will merge files into the primary folder. Continue?[/yellow]"
        )

        panel = Panel(summary_text, title="Merge Confirmation", border_style="yellow")
        self.console.print(panel)

        return Confirm.ask("Proceed with merge?", default=False)

    def _display_errors(self, errors: List[str]) -> None:
        """Display error messages in a separate panel.

        Args:
            errors: List of error messages to display.
        """
        max_display = 10
        displayed_errors = errors[:max_display]
        remaining = len(errors) - max_display

        error_text = "\n".join(f"- {e}" for e in displayed_errors)
        if remaining > 0:
            error_text += f"\n\n... and {remaining} more errors"

        error_panel = Panel(
            error_text,
            title=f"Errors ({len(errors)})",
            border_style="red",
        )
        self.console.print(error_panel)

    def _format_confidence(self, confidence_pct: int) -> str:
        """Format confidence percentage with color coding.

        Args:
            confidence_pct: Confidence as percentage (0-100).

        Returns:
            Formatted string with Rich color markup.
        """
        if confidence_pct >= 90:
            return f"[green]{confidence_pct}%[/green]"
        elif confidence_pct >= 70:
            return f"[yellow]{confidence_pct}%[/yellow]"
        else:
            return f"[red]{confidence_pct}%[/red]"

    def _format_size(self, bytes_size: int) -> str:
        """Convert bytes to human-readable format.

        Args:
            bytes_size: Size in bytes.

        Returns:
            Human-readable size string (e.g., "10.5 MB", "1.2 GB").
        """
        if bytes_size < 1024:
            return f"{bytes_size} B"
        elif bytes_size < 1024 * 1024:
            return f"{bytes_size / 1024:.1f} KB"
        elif bytes_size < 1024 * 1024 * 1024:
            return f"{bytes_size / (1024 * 1024):.1f} MB"
        else:
            return f"{bytes_size / (1024 * 1024 * 1024):.1f} GB"

    def _format_duration(self, seconds: float) -> str:
        """Convert seconds to human-readable duration.

        Args:
            seconds: Duration in seconds.

        Returns:
            Formatted duration string (e.g., "5m 23s").
        """
        if seconds < 0:
            seconds = 0
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"

    def _truncate_name(self, name: str, max_length: int = 60) -> str:
        """Truncate long folder names with ellipsis.

        Args:
            name: The name to potentially truncate.
            max_length: Maximum length before truncation.

        Returns:
            Original name or truncated name with "..." suffix.
        """
        if len(name) > max_length:
            return name[: max_length - 3] + "..."
        return name
