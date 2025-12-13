"""
Computer Data Organization Tool - CLI Interface.

A command-line interface for scanning and merging duplicate computer folders.
This tool helps organize data from multiple computers by finding matching folder
names and intelligently merging their contents.

Usage Examples:
    # Scan for matching folders (read-only)
    python -m mergy scan /path/to/data

    # Scan with custom confidence threshold
    python -m mergy scan /path/to/data --min-confidence 80.0

    # Interactive merge workflow
    python -m mergy merge /path/to/data

    # Dry-run merge (preview without changes)
    python -m mergy merge /path/to/data --dry-run

    # Merge with logging
    python -m mergy merge /path/to/data --log-file merge.log --verbose
"""

import os
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from mergy.orchestration import MergeOrchestrator, MergeLogger
from mergy.models import MergeSummary

__version__ = "1.0.0"

# Initialize Typer app
app = typer.Typer(
    name="mergy",
    help="Computer Data Organization Tool - Find and merge duplicate computer folders.",
    add_completion=False,
    no_args_is_help=True,
)

# Rich console for consistent output formatting
console = Console()


def version_callback(value: bool) -> None:
    """
    Print the program version and exit if the version option was requested.
    
    Parameters:
        value (bool): Whether the version option was requested; when True this prints the version and exits.
    """
    if value:
        console.print(f"Computer Data Organization Tool v{__version__}")
        raise typer.Exit()


def validate_base_path(base_path: Path) -> None:
    """
    Validate that base_path exists, is a directory, and is readable.
    
    If any check fails, prints an error to the console and exits the program with status code 1.
    
    Parameters:
        base_path (Path): Path to validate.
    
    Raises:
        typer.Exit: Exits with status code 1 when validation fails.
    """
    # Check if path exists
    if not base_path.exists():
        console.print(
            f"[red]Error:[/red] Base path does not exist: {base_path}"
        )
        raise typer.Exit(1)

    # Check if path is a directory
    if not base_path.is_dir():
        console.print(
            f"[red]Error:[/red] Base path is not a directory: {base_path}"
        )
        raise typer.Exit(1)

    # Check if path is readable
    if not os.access(base_path, os.R_OK):
        console.print(
            f"[red]Error:[/red] Permission denied - cannot read: {base_path}"
        )
        raise typer.Exit(1)


def validate_confidence(value: float) -> float:
    """
    Validate that a confidence percentage is within the inclusive range 0 to 100.
    
    Parameters:
        value (float): Confidence percentage to validate (expected 0–100).
    
    Returns:
        float: The validated confidence value.
    
    Raises:
        typer.BadParameter: If `value` is less than 0 or greater than 100.
    """
    if not 0.0 <= value <= 100.0:
        raise typer.BadParameter("Confidence must be between 0 and 100")
    return value


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-v",
        callback=version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """
    CLI entry callback that processes global options for the mergy application.
    
    Parameters:
        version (Optional[bool]): Typer-managed flag for the `--version`/`-v` option; when set, the configured callback prints the program version and exits.
    """
    pass


@app.command()
def scan(
    base_path: Path = typer.Argument(
        ...,
        help="Base directory containing folders to scan.",
        exists=False,  # We do our own validation
    ),
    min_confidence: float = typer.Option(
        70.0,
        "--min-confidence",
        "-c",
        help="Minimum confidence threshold for matches (0-100).",
        callback=validate_confidence,
    ),
    log_file: Optional[Path] = typer.Option(
        None,
        "--log-file",
        "-l",
        help="Path for log file output.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-V",
        help="Enable verbose output.",
    ),
) -> None:
    """
    Scan for matching folders without merging.

    Analyzes the base directory for folders that appear to be duplicates
    based on name similarity. Displays match groups above the confidence
    threshold without making any changes.
    """
    # Validate base path
    validate_base_path(base_path)

    # Create logger if log file specified
    logger_instance: Optional[MergeLogger] = None
    if log_file:
        try:
            logger_instance = MergeLogger(log_file, mode="SCAN ONLY")
        except PermissionError:
            console.print(
                f"[yellow]Warning:[/yellow] Cannot write to log file: {log_file}. "
                "Continuing without logging."
            )
            logger_instance = None
        except OSError as e:
            console.print(
                f"[yellow]Warning:[/yellow] Failed to create log file: {e}. "
                "Continuing without logging."
            )
            logger_instance = None

    try:
        # Create orchestrator and run scan workflow
        orchestrator = MergeOrchestrator(
            base_path=base_path,
            min_confidence=min_confidence,
            dry_run=True,  # Scan is always read-only
            verbose=verbose,
            logger_instance=logger_instance,
        )

        matches = orchestrator.run_scan_workflow()

        # Display results summary
        if matches:
            console.print(
                f"\n[green]Found {len(matches)} match group(s) "
                f"above {min_confidence}% confidence.[/green]"
            )
        else:
            console.print(
                f"\n[yellow]No matching folders found "
                f"above {min_confidence}% confidence.[/yellow]"
            )

        if log_file and logger_instance:
            console.print(f"[dim]Log written to: {log_file}[/dim]")

    except KeyboardInterrupt:
        console.print("\n[yellow]Scan interrupted by user.[/yellow]")
        raise typer.Exit(130)

    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    except PermissionError as e:
        console.print(f"[red]Error:[/red] Permission denied - {e}")
        raise typer.Exit(1)

    except OSError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    finally:
        if logger_instance:
            logger_instance.close()


@app.command()
def merge(
    base_path: Path = typer.Argument(
        ...,
        help="Base directory containing folders to merge.",
        exists=False,  # We do our own validation
    ),
    min_confidence: float = typer.Option(
        70.0,
        "--min-confidence",
        "-c",
        help="Minimum confidence threshold for matches (0-100).",
        callback=validate_confidence,
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-n",
        help="Simulate merge without making changes.",
    ),
    log_file: Optional[Path] = typer.Option(
        None,
        "--log-file",
        "-l",
        help="Path for log file output.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-V",
        help="Enable verbose output.",
    ),
) -> None:
    """
    Perform an interactive merge workflow for duplicate folders under the given base directory.
    
    Runs a five-phase workflow: scan for matching folder groups, interactively select folders to merge,
    analyze and preview proposed operations, execute the merge (or simulate when dry-run is enabled),
    and present a summary of results and statistics. May modify files unless `dry_run` is True.
    
    Parameters:
        base_path (Path): Base directory containing folders to merge.
        min_confidence (float): Minimum confidence threshold (0-100) required for matches to be considered.
        dry_run (bool): If True, simulate the merge without modifying any files.
        log_file (Optional[Path]): Path to write an operation log; failure to create the log causes the command to exit.
        verbose (bool): Enable verbose output from the workflow.
    
    Notes:
        The command exits with code 130 if interrupted by the user and with code 1 on permission, validation,
        or I/O errors (including disk-full conditions).
    """
    # Validate base path
    validate_base_path(base_path)

    # Additional validation for merge: need write permissions
    if not dry_run and not os.access(base_path, os.W_OK):
        console.print(
            f"[red]Error:[/red] Permission denied - cannot write to: {base_path}"
        )
        console.print(
            "[dim]Tip: Use --dry-run to preview changes without write access.[/dim]"
        )
        raise typer.Exit(1)

    # Create logger if log file specified
    logger_instance: Optional[MergeLogger] = None
    mode = "DRY RUN" if dry_run else "LIVE MERGE"
    if log_file:
        try:
            logger_instance = MergeLogger(log_file, mode=mode)
        except PermissionError:
            console.print(
                f"[red]Error:[/red] Cannot write to log file: {log_file}"
            )
            raise typer.Exit(1)
        except OSError as e:
            console.print(f"[red]Error:[/red] Failed to create log file: {e}")
            raise typer.Exit(1)

    try:
        # Display mode indicator
        if dry_run:
            console.print("[yellow][DRY RUN MODE][/yellow] No files will be modified.\n")

        # Create orchestrator and run merge workflow
        orchestrator = MergeOrchestrator(
            base_path=base_path,
            min_confidence=min_confidence,
            dry_run=dry_run,
            verbose=verbose,
            logger_instance=logger_instance,
        )

        summary = orchestrator.run_merge_workflow()

        # Validate that summary is a MergeSummary instance
        if not isinstance(summary, MergeSummary):
            console.print(
                "[red]Error:[/red] Merge workflow returned unexpected result type. "
                "Expected MergeSummary, got " + type(summary).__name__
            )
            raise typer.Exit(1)

        # Check for errors in summary
        if summary.errors:
            console.print(
                f"\n[yellow]Completed with {len(summary.errors)} error(s).[/yellow]"
            )

        if log_file and logger_instance:
            console.print(f"\n[dim]Log written to: {log_file}[/dim]")

        # Return appropriate exit code
        if summary.interrupted:
            raise typer.Exit(130)
        elif summary.errors:
            raise typer.Exit(1)

    except KeyboardInterrupt:
        console.print("\n[yellow]Merge interrupted by user.[/yellow]")
        raise typer.Exit(130)

    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    except PermissionError as e:
        console.print(f"[red]Error:[/red] Permission denied - {e}")
        raise typer.Exit(1)

    except OSError as e:
        # Check for disk full error
        if "No space left on device" in str(e) or getattr(e, 'errno', None) == 28:
            console.print(
                "[red]Error:[/red] Disk full - merge operation aborted."
            )
            console.print(
                "[dim]Some files may have been partially copied. "
                "Please free up disk space and retry.[/dim]"
            )
        else:
            console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    finally:
        if logger_instance:
            logger_instance.close()


if __name__ == "__main__":
    app()