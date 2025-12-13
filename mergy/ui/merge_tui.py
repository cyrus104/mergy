"""
Interactive terminal user interface for the Computer Data Organization Tool.

This module provides the MergeTUI class, which uses the Rich library to create
an interactive terminal UI for folder merge operations, including progress
tracking, user prompts, and summary displays.
"""

from typing import List

from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.prompt import Prompt, Confirm
from rich.panel import Panel

from mergy.models import ComputerFolder, FolderMatch, MergeSelection, FileConflict, MergeOperation


class MergeTUI:
    """
    Interactive terminal user interface using Rich library.

    Provides display methods for match groups, prompts for user selection,
    and progress tracking during merge operations.
    """

    def __init__(self, dry_run: bool = False) -> None:
        """
        Initialize TUI with Rich Console.

        Args:
            dry_run: If True, display [DRY RUN] prefix in progress messages.
        """
        self.console = Console()
        self.dry_run = dry_run

    def _format_size(self, size_bytes: int) -> str:
        """
        Format byte size to human-readable string.

        Args:
            size_bytes: Size in bytes.

        Returns:
            Formatted string (e.g., "1.5 GB", "256 MB", "12 KB").
        """
        if size_bytes >= 1024 ** 3:
            return f"{size_bytes / (1024 ** 3):.1f} GB"
        elif size_bytes >= 1024 ** 2:
            return f"{size_bytes / (1024 ** 2):.1f} MB"
        elif size_bytes >= 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes} B"

    def _format_date_range(self, folder: ComputerFolder) -> str:
        """
        Format date range for a folder.

        Args:
            folder: ComputerFolder with date information.

        Returns:
            Formatted date range string or "Empty folder" if no files.
        """
        if folder.oldest_file_date is None or folder.newest_file_date is None:
            return "Empty folder"

        oldest = folder.oldest_file_date.strftime("%Y-%m-%d")
        newest = folder.newest_file_date.strftime("%Y-%m-%d")

        if oldest == newest:
            return oldest
        return f"{oldest} to {newest}"

    def display_match_group(
        self, match: FolderMatch, current: int, total: int
    ) -> None:
        """
        Display a match group with folder details.

        Args:
            match: FolderMatch containing folders to display.
            current: Current match group number (1-based).
            total: Total number of match groups.
        """
        # Progress indicator
        progress_filled = int((current / total) * 12)
        progress_bar = "█" * progress_filled + "░" * (12 - progress_filled)
        self.console.print(
            f"\n[bold cyan][{progress_bar}] {current}/{total} match groups[/bold cyan]"
        )

        # Create table for folder details
        table = Table(title=f"Match Group: {match.base_name}", show_header=True)
        table.add_column("Index", style="cyan", width=6)
        table.add_column("Folder Name", style="white")
        table.add_column("Files", justify="right", style="green")
        table.add_column("Size", justify="right", style="yellow")
        table.add_column("Date Range", style="magenta")

        for idx, folder in enumerate(match.folders, start=1):
            table.add_row(
                str(idx),
                folder.name,
                str(folder.file_count),
                self._format_size(folder.total_size),
                self._format_date_range(folder)
            )

        self.console.print(table)

        # Display confidence and match reason
        reason_text = match.match_reason.value.replace("_", " ").title()
        panel = Panel(
            f"[bold]Confidence:[/bold] {match.confidence:.0f}%\n"
            f"[bold]Match Reason:[/bold] {reason_text}",
            title="Match Details",
            border_style="blue"
        )
        self.console.print(panel)

    def prompt_merge_action(self) -> str:
        """
        Prompt user for merge action.

        Returns:
            User's choice: 'm' (merge), 's' (skip), or 'q' (quit).
        """
        while True:
            choice = Prompt.ask(
                "Action",
                choices=["m", "s", "q"],
                default="s"
            )
            if choice in ["m", "s", "q"]:
                return choice

    def prompt_folder_selection(self, match: FolderMatch) -> List[int]:
        """
        Prompt user to select folders to merge.

        Args:
            match: FolderMatch containing folders to choose from.

        Returns:
            List of selected folder indices (0-based).
        """
        self.console.print("\n[bold]Select folders to merge:[/bold]")
        for idx, folder in enumerate(match.folders, start=1):
            self.console.print(f"  {idx}. {folder.name}")

        while True:
            selection = Prompt.ask(
                "Enter folder numbers (e.g., '1 2 3' or 'all')"
            )

            if selection.lower() == "all":
                return list(range(len(match.folders)))

            try:
                indices = [int(x) - 1 for x in selection.split()]
                # Validate all indices are in range
                if all(0 <= idx < len(match.folders) for idx in indices):
                    if len(indices) >= 2:
                        return indices
                    else:
                        self.console.print(
                            "[red]Please select at least 2 folders to merge.[/red]"
                        )
                else:
                    self.console.print(
                        f"[red]Invalid selection. Please enter numbers 1-{len(match.folders)}.[/red]"
                    )
            except ValueError:
                self.console.print(
                    "[red]Invalid input. Enter space-separated numbers or 'all'.[/red]"
                )

    def prompt_primary_selection(self, selected_folders: List[ComputerFolder]) -> int:
        """
        Prompt user to select the primary (destination) folder.

        Args:
            selected_folders: List of folders selected for merge.

        Returns:
            Index of selected primary folder (0-based).
        """
        self.console.print("\n[bold]Select primary folder (destination):[/bold]")
        for idx, folder in enumerate(selected_folders, start=1):
            self.console.print(
                f"  {idx}. {folder.name} ({folder.file_count} files, "
                f"{self._format_size(folder.total_size)})"
            )

        while True:
            selection = Prompt.ask(
                "Primary folder number",
                default="1"
            )

            try:
                idx = int(selection) - 1
                if 0 <= idx < len(selected_folders):
                    return idx
                else:
                    self.console.print(
                        f"[red]Invalid selection. Please enter a number 1-{len(selected_folders)}.[/red]"
                    )
            except ValueError:
                self.console.print("[red]Invalid input. Enter a number.[/red]")

    def confirm_merge(self, selection: MergeSelection) -> bool:
        """
        Display merge summary and confirm with user.

        Args:
            selection: MergeSelection to confirm.

        Returns:
            True if user confirms, False otherwise.
        """
        # Calculate totals
        total_files = sum(f.file_count for f in selection.merge_from)
        total_size = sum(f.total_size for f in selection.merge_from)

        merge_from_list = "\n".join(
            f"  • {f.name}" for f in selection.merge_from
        )

        summary = (
            f"[bold]Primary folder:[/bold] {selection.primary.name}\n"
            f"[bold]Path:[/bold] {selection.primary.path}\n\n"
            f"[bold]Merging from:[/bold]\n{merge_from_list}\n\n"
            f"[bold]Total files to process:[/bold] {total_files}\n"
            f"[bold]Total size:[/bold] {self._format_size(total_size)}"
        )

        panel = Panel(summary, title="Merge Summary", border_style="green")
        self.console.print(panel)

        return Confirm.ask("Proceed with merge?")

    def display_analysis_summary(
        self,
        operation: MergeOperation,
        conflicts: List[FileConflict]
    ) -> None:
        """
        Display analysis results before execution.

        Args:
            operation: MergeOperation with analysis results.
            conflicts: List of detected conflicts.
        """
        table = Table(title="Merge Analysis", show_header=True)
        table.add_column("Category", style="cyan")
        table.add_column("Count", justify="right", style="white")

        table.add_row(
            "[green]New files to copy[/green]",
            str(operation.files_copied)
        )
        table.add_row(
            "[yellow]Duplicate files to skip[/yellow]",
            str(operation.files_skipped)
        )
        table.add_row(
            "[red]Conflicts to resolve[/red]",
            str(operation.conflicts_resolved)
        )

        self.console.print(table)

        if conflicts:
            self.console.print("\n[bold red]Conflicts detected:[/bold red]")
            for conflict in conflicts:
                newer = "primary" if conflict.primary_ctime >= conflict.conflict_ctime else "merge-from"
                self.console.print(
                    f"  • {conflict.relative_path} - {newer} file is newer"
                )

    def show_progress_bar(self, description: str) -> Progress:
        """
        Create a Rich Progress context manager for file operations.

        Args:
            description: Description to show in progress bar.

        Returns:
            Rich Progress instance to use as context manager.
        """
        prefix = "[DRY RUN] " if self.dry_run else ""
        return Progress(
            SpinnerColumn(),
            TextColumn(f"[progress.description]{prefix}{{task.description}}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            console=self.console
        )

    def display_summary(
        self,
        operations: List[MergeOperation],
        duration: float
    ) -> None:
        """
        Display final summary of all merge operations.

        Args:
            operations: List of completed MergeOperation objects.
            duration: Total workflow duration in seconds.
        """
        # Calculate totals
        total_copied = sum(op.files_copied for op in operations)
        total_skipped = sum(op.files_skipped for op in operations)
        total_conflicts = sum(op.conflicts_resolved for op in operations)
        total_removed = sum(op.folders_removed for op in operations)
        all_errors = [err for op in operations for err in op.errors]

        # Format duration
        minutes = int(duration // 60)
        seconds = int(duration % 60)
        duration_str = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"

        # Determine status color
        if all_errors:
            border_style = "red"
            status = "[red]Completed with errors[/red]"
        else:
            border_style = "green"
            status = "[green]Completed successfully[/green]"

        summary = (
            f"[bold]Status:[/bold] {status}\n"
            f"[bold]Merge operations:[/bold] {len(operations)}\n"
            f"[bold]Files copied:[/bold] [green]{total_copied:,}[/green]\n"
            f"[bold]Files skipped (duplicates):[/bold] [yellow]{total_skipped:,}[/yellow]\n"
            f"[bold]Conflicts resolved:[/bold] [red]{total_conflicts:,}[/red]\n"
            f"[bold]Empty folders removed:[/bold] {total_removed:,}\n"
            f"[bold]Duration:[/bold] {duration_str}"
        )

        panel = Panel(summary, title="Merge Summary", border_style=border_style)
        self.console.print(panel)

        if all_errors:
            self.console.print("\n[bold red]Errors encountered:[/bold red]")
            for error in all_errors[:10]:  # Show first 10 errors
                self.console.print(f"  • {error}")
            if len(all_errors) > 10:
                self.console.print(f"  ... and {len(all_errors) - 10} more errors")
