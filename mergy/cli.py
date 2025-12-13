"""Mergy CLI - Computer Data Organization Tool.

A command-line interface for intelligently merging folders across multiple
computer backup directories using fuzzy matching and user-guided selection.

Usage examples:
    # Basic scan
    mergy scan /path/to/computerNames

    # Scan with lower confidence threshold
    mergy scan /path/to/computerNames --min-confidence 50

    # Dry-run merge to preview changes
    mergy merge /path/to/computerNames --dry-run

    # Merge with custom log file
    mergy merge /path/to/computerNames --log-file ~/merge-2024.log

    # Verbose output for debugging
    mergy merge /path/to/computerNames --verbose
"""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from mergy import __version__
from mergy.orchestration import MergeOrchestrator

# Create Typer app with rich markup enabled
app = typer.Typer(
    name="mergy",
    help="Computer Data Organization Tool for intelligently merging folders.",
    rich_markup_mode="rich",
    add_completion=False,
)

console = Console()


def version_callback(value: bool) -> None:
    """Display version and exit."""
    if value:
        console.print(f"mergy version {__version__}")
        raise typer.Exit()


@app.callback()
def main_callback(
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        help="Show version and exit.",
        callback=version_callback,
        is_eager=True,
    ),
) -> None:
    """Mergy - Computer Data Organization Tool.

    Intelligently merge folders across multiple computer backup directories
    using fuzzy matching and user-guided selection.
    """
    pass


@app.command()
def scan(
    path: Path = typer.Argument(
        ...,
        help="Path to the directory containing folders to scan.",
        exists=False,  # We validate manually for better error messages
    ),
    min_confidence: float = typer.Option(
        70.0,
        "--min-confidence",
        "-c",
        help="Minimum match confidence (0-100). Default: 70",
        min=0.0,
        max=100.0,
    ),
    log_file: Optional[Path] = typer.Option(
        None,
        "--log-file",
        "-l",
        help="Path to log file. If not specified, a timestamped filename is generated.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-V",
        help="Display additional details during execution.",
    ),
) -> None:
    """Analyze folders without modification.

    Scans immediate subdirectories of the specified path, identifies potential
    matches using fuzzy name matching, and displays results. No files are
    modified during scanning.

    The scan results show groups of folders that appear to represent the same
    computer based on naming patterns (e.g., 'computer-01', 'computer-01-backup',
    'computer-01.old').
    """
    # Validate path exists
    if not path.exists():
        console.print(f"[red]Error: Path does not exist: {path}[/red]")
        raise typer.Exit(1)

    # Validate path is a directory
    if not path.is_dir():
        console.print(f"[red]Error: Path is not a directory: {path}[/red]")
        raise typer.Exit(1)

    # Validate log file path if provided
    if log_file is not None and log_file.is_dir():
        console.print(f"[red]Error: Log file path is a directory: {log_file}[/red]")
        raise typer.Exit(1)

    # Convert confidence from 0-100 scale to 0.0-1.0
    confidence_normalized = min_confidence / 100.0

    try:
        orchestrator = MergeOrchestrator(
            base_path=path,
            min_confidence=confidence_normalized,
            log_file_path=log_file,
            dry_run=False,
            verbose=verbose,
        )

        matches = orchestrator.scan()

        # Handle no matches case
        if not matches:
            console.print(
                "\n[yellow]No matches found above confidence threshold. "
                "Try lowering --min-confidence[/yellow]"
            )

    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Scan cancelled by user.[/yellow]")
        raise typer.Exit(1)
    except OSError as e:
        console.print(f"[red]Error: File system error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def merge(
    path: Path = typer.Argument(
        ...,
        help="Path to the directory containing folders to merge.",
        exists=False,  # We validate manually for better error messages
    ),
    min_confidence: float = typer.Option(
        70.0,
        "--min-confidence",
        "-c",
        help="Minimum match confidence (0-100). Default: 70",
        min=0.0,
        max=100.0,
    ),
    log_file: Optional[Path] = typer.Option(
        None,
        "--log-file",
        "-l",
        help="Path to log file. If not specified, a timestamped filename is generated.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-V",
        help="Display additional details during execution.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-n",
        help="Simulate merge without making changes. Enables safe testing.",
    ),
) -> None:
    """Interactive merge process.

    Guides you through selecting and merging folder groups identified during
    scanning. For each match group, you can select which folder to keep as
    primary and which folders to merge from.

    The merge process:
    1. Scans folders and identifies matches
    2. Presents each match group for review
    3. Allows selection of primary folder and merge sources
    4. Copies unique files to primary folder
    5. Optionally removes source folders after successful merge

    Use --dry-run to preview changes without modifying any files.
    """
    # Validate path exists
    if not path.exists():
        console.print(f"[red]Error: Path does not exist: {path}[/red]")
        raise typer.Exit(1)

    # Validate path is a directory
    if not path.is_dir():
        console.print(f"[red]Error: Path is not a directory: {path}[/red]")
        raise typer.Exit(1)

    # Validate log file path if provided
    if log_file is not None and log_file.is_dir():
        console.print(f"[red]Error: Log file path is a directory: {log_file}[/red]")
        raise typer.Exit(1)

    # Convert confidence from 0-100 scale to 0.0-1.0
    confidence_normalized = min_confidence / 100.0

    if dry_run:
        console.print("[cyan]Running in dry-run mode - no changes will be made[/cyan]\n")

    try:
        orchestrator = MergeOrchestrator(
            base_path=path,
            min_confidence=confidence_normalized,
            log_file_path=log_file,
            dry_run=dry_run,
            verbose=verbose,
        )

        summary = orchestrator.merge()

        # Handle no operations case
        if summary.total_operations == 0 and not summary.errors:
            console.print(
                "\n[yellow]No merge operations performed.[/yellow]"
            )

    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Merge cancelled by user.[/yellow]")
        raise typer.Exit(1)
    except OSError as e:
        console.print(f"[red]Error: File system error: {e}[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
