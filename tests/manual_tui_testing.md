# Manual TUI Testing Scenarios for MergeTUI

This document provides step-by-step scenarios for manually testing the `MergeTUI` class in `mergy/ui/merge_tui.py`. These tests verify visual appearance, user experience, and edge cases that are difficult to automate.

## Overview

The `MergeTUI` class provides the interactive terminal user interface for folder merge operations. Key methods to exercise:

| Method | Location | Purpose |
|--------|----------|---------|
| `display_scan_summary` | `merge_tui.py:60-101` | Shows scan results in a formatted table |
| `review_match_groups` | `merge_tui.py:103-167` | Interactive workflow for reviewing and selecting matches |
| `display_merge_summary` | `merge_tui.py:169-200` | Shows final statistics after merges complete |
| `create_progress_callback` | `merge_tui.py:202-238` | Creates progress bars for file operations |

## Prerequisites

- Python 3.10+ with mergy installed
- Terminal with color support (80+ columns recommended)
- Test directories with sample folder structures

---

## Scenario 1: Full Merge Workflow

**Objective**: Verify the complete merge workflow from scan to completion.

**Methods Exercised**:
- `display_scan_summary` - Scan results display
- `review_match_groups` - Interactive selection loop
- `_display_match_group` - Individual group display
- `_prompt_action` - Action selection prompt
- `_process_merge_action` - Merge flow handling
- `_select_folders_to_merge` - Folder selection
- `_select_primary_folder` - Primary folder selection
- `_confirm_merge` - Confirmation panel
- `display_merge_summary` - Final summary
- `create_progress_callback` - Progress tracking during file operations

### Preconditions

Create a test directory structure:

```bash
mkdir -p /tmp/mergy-test/computers
cd /tmp/mergy-test/computers

# Create exact prefix match group
mkdir -p "135897-ntp"
mkdir -p "135897-ntp.newspace"
echo "file1 content" > "135897-ntp/data.txt"
echo "file2 content" > "135897-ntp.newspace/data.txt"
echo "shared content" > "135897-ntp/shared.txt"
echo "different content" > "135897-ntp.newspace/shared.txt"
echo "unique" > "135897-ntp.newspace/unique.txt"

# Create normalized match group
mkdir -p "192.168.1.5-computer01"
mkdir -p "192.168.1.5 computer01"
echo "log1" > "192.168.1.5-computer01/system.log"
echo "log2" > "192.168.1.5 computer01/system.log"

# Create unrelated folder
mkdir -p "unrelated-folder"
echo "other" > "unrelated-folder/other.txt"
```

### Commands to Run

```bash
# Dry run first (recommended)
python mergy.py merge /tmp/mergy-test/computers --dry-run

# Live merge
python mergy.py merge /tmp/mergy-test/computers
```

### Key Prompts Expected

1. **Scan Summary Panel** (`display_scan_summary`):
   - "Scan Results" panel with blue border
   - "Folders scanned: X" count
   - "Match groups found: Y" count
   - "Confidence threshold: 70%" (or configured value)
   - Table with columns: Group #, Confidence, Match Type, Folders

2. **Progress Bar** (`review_match_groups`):
   - "Reviewing match groups: 1/2" description
   - Visual progress bar advancing

3. **Match Group Display** (`_display_match_group`):
   - Blue-bordered panel titled "Match Group 1 - 95% confidence (exact_prefix)"
   - Table with columns: #, Folder Name, Files, Size, Date Range
   - Each folder numbered for selection

4. **Action Prompt** (`_prompt_action`):
   - "(m)erge, (s)kip, (q)uit" prompt
   - Default is "s" (skip)

5. **Folder Selection** (`_select_folders_to_merge`):
   - "Select folders to merge (e.g., '1 2 3' or 'all')"
   - Default is "all" for 2-folder groups

6. **Primary Folder Selection** (`_select_primary_folder`):
   - "Select primary folder (destination):"
   - Numbered list with "[recommended]" on largest folder
   - Default is the recommended folder

7. **Merge Confirmation** (`_confirm_merge`):
   - Yellow-bordered "Merge Confirmation" panel
   - Shows primary folder in green
   - Lists "Merging from:" folders
   - "Proceed with merge?" prompt (default: No)

8. **Merge Summary** (`display_merge_summary`):
   - Green-bordered "Merge Summary" panel (or yellow if dry-run)
   - Statistics table: Total operations, Files copied, Files skipped, Conflicts resolved, Folders removed, Duration

### Expected Visual Outcomes

- Progress bar advances from "1/2" to "2/2" as groups are reviewed
- Confidence percentages are color-coded (green >=90%, yellow >=70%, red <70%)
- Long folder names are truncated with "..." and full paths shown in caption
- [DRY RUN] indicator appears in summary when using --dry-run flag
- Duration formatted as "Xm Ys" (e.g., "5m 23s")

---

## Scenario 2: Long Folder Names

**Objective**: Verify folder names are truncated gracefully without breaking layout.

**Methods Exercised**:
- `display_scan_summary` - Table truncation in scan view
- `_display_match_group` - Detail view truncation
- `_truncate_name` - Internal truncation helper

### Preconditions

Create folders with very long names (>60 characters):

```bash
mkdir -p /tmp/mergy-long-test/computers
cd /tmp/mergy-long-test/computers

# Create folders with 80+ character names
long_name="this-is-a-very-long-folder-name-that-exceeds-sixty-characters-for-testing-purposes"
mkdir -p "${long_name}"
mkdir -p "${long_name}.backup"
echo "content" > "${long_name}/file.txt"
echo "content2" > "${long_name}.backup/file.txt"
```

### Commands to Run

```bash
python mergy.py scan /tmp/mergy-long-test/computers
```

### Key Prompts Expected

1. **Scan Summary Table** (`display_scan_summary`):
   - Folder names truncated to 50 characters with "..."
   - Full names visible in some context

2. **Match Group Display** (`_display_match_group`):
   - Names truncated to 60 characters in table
   - "Full paths:" caption section showing complete folder names with indices

### Expected Visual Outcomes

- Table columns remain properly aligned despite truncation
- Ellipsis ("...") appears at end of truncated names
- Full paths are accessible below the table for reference
- No display corruption or line wrapping issues
- Caption format: "Full paths:\n  [1] full-path-here\n  [2] full-path-here"

---

## Scenario 3: Keyboard Interrupt Handling

**Objective**: Verify graceful exit when user presses Ctrl+C.

**Methods Exercised**:
- `review_match_groups` - Exception handling in main loop
- Progress bar update on early exit

### Preconditions

Use the test structure from Scenario 1.

### Commands to Run

```bash
python mergy.py merge /tmp/mergy-test/computers
```

### Test Steps

1. Wait for the first match group to display
2. Press `Ctrl+C` during the action prompt

### Key Prompts Expected

1. **Interruption Message**:
   - Yellow message: "Operation cancelled by user."
   - Displayed via console.print with yellow styling

2. **Progress Bar State** (`review_match_groups`):
   - Progress should reflect actual groups reviewed (NOT 100%)
   - If cancelled at group 1 of 2, progress shows partial completion
   - Description may indicate review was interrupted

### Expected Visual Outcomes

- Yellow "Operation cancelled by user." message appears
- Application exits gracefully without stack trace
- Progress bar shows partial completion reflecting last reviewed group
- Returns empty list or partial selections to caller
- No data corruption occurs

---

## Scenario 4: Invalid Input Recovery

**Objective**: Verify the TUI handles invalid input gracefully.

**Methods Exercised**:
- `_prompt_action` - Invalid action handling
- `_select_folders_to_merge` - Invalid selection handling

### Preconditions

Use the test structure from Scenario 1.

### Commands to Run

```bash
python mergy.py merge /tmp/mergy-test/computers
```

### Test Steps

1. At "(m)erge, (s)kip, (q)uit" prompt:
   - Type "x" and press Enter
   - Observe: Rich Prompt shows available choices and re-prompts

2. Select "m" to merge, then at folder selection:
   - Type "abc" (non-numeric) and press Enter
   - Observe: Red error message about invalid selection
   - Type "99" (out of range) and press Enter
   - Observe: Red error message with valid range (1-N)
   - Type empty string and press Enter
   - Observe: For 2-folder groups, selects all; otherwise prompts again

### Key Prompts Expected

1. **Invalid Action** (`_prompt_action`):
   - Rich's Prompt.ask handles invalid choices internally
   - Shows valid choices and re-prompts

2. **Invalid Folder Selection** (`_select_folders_to_merge`):
   - "[red]Invalid selection 'abc'. Please enter numbers (1-N) or 'all'.[/red]"
   - "[red]Index 99 out of range[/red]" (via ValueError in loop)

### Expected Visual Outcomes

- Red error messages for invalid input
- Prompts repeat until valid input received
- No application crash
- User can eventually proceed with valid selection
- Error messages clearly explain expected format

---

## Scenario 5: Dry-Run Summary Behavior

**Objective**: Verify dry-run indicator and visual distinction.

**Methods Exercised**:
- `display_merge_summary` - Dry run mode display
- Panel styling differences between dry-run and live mode

### Preconditions

Create a structure with files that will produce conflicts:

```bash
mkdir -p /tmp/mergy-dryrun-test/computers
cd /tmp/mergy-dryrun-test/computers

mkdir -p "server01"
mkdir -p "server01-backup"

# Create conflicting files (same name, different content)
echo "primary content" > "server01/config.txt"
echo "backup content" > "server01-backup/config.txt"

# Create unique files
echo "primary only" > "server01/primary.txt"
echo "backup only" > "server01-backup/backup.txt"

# Create duplicate files (same content)
echo "identical" > "server01/shared.txt"
echo "identical" > "server01-backup/shared.txt"
```

### Commands to Run

```bash
# Dry-run mode
python mergy.py merge /tmp/mergy-dryrun-test/computers --dry-run
```

### Test Steps

1. Select "m" to merge the match group
2. Select "all" folders
3. Choose primary folder (or accept recommended)
4. Confirm the merge with "y"

### Key Prompts Expected

1. **Dry-Run Indicator** (`display_merge_summary`):
   - Title: "Merge Summary [yellow][DRY RUN][/yellow]"
   - Yellow border on summary panel (instead of green)

2. **Statistics Table**:
   - Shows what would have happened
   - "Total operations" count
   - "Files copied" count of unique files
   - "Files skipped (duplicates)" count
   - "Conflicts resolved" count
   - "Folders removed" count
   - "Duration" in Xm Ys format

### Expected Visual Outcomes

- Yellow "[DRY RUN]" indicator prominently displayed in title
- Yellow panel border distinguishes from live merge (green)
- Statistics reflect planned operations accurately
- No actual file system changes occur
- Verification: `ls` commands show original structure unchanged

---

## Progress Callback Testing

**Objective**: Verify `create_progress_callback` returns correct tuple and functions properly.

**Methods Exercised**:
- `create_progress_callback` - Returns `(Progress, Callable[[int], None])` tuple

### Manual Test via Python REPL

```python
import io
from rich.console import Console
from mergy.ui import MergeTUI

# Create TUI with captured output
output = io.StringIO()
console = Console(file=output, force_terminal=True, width=80)
tui = MergeTUI(console=console)

# Create progress callback - returns (Progress, callback) tuple
progress, callback = tui.create_progress_callback("test-folder", total_files=100)

# Verify return types
print(f"Progress type: {type(progress)}")  # Should be rich.progress.Progress
print(f"Callback callable: {callable(callback)}")  # Should be True

# Use Progress as context manager (required usage pattern)
with progress:
    callback(0)    # 0% complete
    callback(50)   # 50% complete
    callback(100)  # 100% complete

# View output
print(output.getvalue())
```

### Expected Visual Outcomes

- Progress bar shows "Merging test-folder..."
- Bar advances from 0% to 50% to 100%
- Time remaining estimate updates
- Bar completes fully at 100%

### API Contract Note

The `create_progress_callback` method returns a tuple of `(Progress, Callable[[int], None])`. The caller is responsible for:
1. Using the `Progress` instance as a context manager (`with progress:`)
2. Calling the callback with the number of completed items

See `tests/test_merge_tui.py` for automated tests of this behavior.

---

## Cross-Reference: MergeTUI Methods and Test Scenarios

| Method | Line | Description | Test Scenarios |
|--------|------|-------------|----------------|
| `display_scan_summary` | 60-101 | Shows scan results table | 1, 2 |
| `review_match_groups` | 103-167 | Interactive review loop with progress | 1, 3, 4 |
| `display_merge_summary` | 169-200 | Final statistics display | 1, 5 |
| `create_progress_callback` | 202-238 | Progress bar factory | 1, Progress Callback Testing |
| `_display_match_group` | 240-280 | Single group detail view | 1, 2 |
| `_prompt_action` | 282-299 | m/s/q action prompt | 1, 4 |
| `_process_merge_action` | 301-333 | Merge workflow handler | 1 |
| `_select_folders_to_merge` | 335-384 | Folder selection prompt | 1, 4 |
| `_select_primary_folder` | 386-416 | Primary folder selection | 1 |
| `_confirm_merge` | 418-440 | Confirmation panel and prompt | 1 |
| `_display_errors` | 442-461 | Error panel display | 5 (with errors) |
| `_format_confidence` | 463-477 | Color-coded percentage | 1, 2 |
| `_format_size` | 479-495 | Human-readable size | 1, 2 |
| `_format_duration` | 497-510 | Duration formatting | 1, 5 |
| `_truncate_name` | 512-524 | Name truncation with ellipsis | 2 |

---

## Related Files

- **Implementation**: `mergy/ui/merge_tui.py` - Main TUI class
- **Automated Tests**: `tests/test_merge_tui.py` - Unit and integration tests
- **Test Fixtures**: `tests/conftest.py` - Shared fixtures (`sample_folder_matches`, `sample_merge_summary`, etc.)

---

## General UI Verification Checklist

For all scenarios, verify:

- [ ] Panel borders render correctly (blue for info, green for success, yellow for warning, red for error)
- [ ] Table columns are aligned
- [ ] Colors display properly (terminal with color support)
- [ ] Progress bars animate smoothly
- [ ] Text is readable and not truncated unexpectedly
- [ ] Numbers are formatted with thousands separators (e.g., "1,234")
- [ ] Window resizing doesn't break layout
- [ ] Keyboard shortcuts work (Ctrl+C for interrupt)

---

## Terminal Compatibility Notes

1. **Width**: Tests should be run in terminals of varying widths (80, 120, 160 columns) to verify table formatting.

2. **Color Support**: Some terminals may not support Rich's color output. Test with `TERM=dumb` to verify fallback behavior:
   ```bash
   TERM=dumb python mergy.py scan /tmp/mergy-test/computers
   ```

3. **Platform Differences**: Test on Linux, macOS, and Windows to verify consistent behavior across platforms.

---

## Cleanup

After testing, remove test directories:

```bash
rm -rf /tmp/mergy-test
rm -rf /tmp/mergy-long-test
rm -rf /tmp/mergy-dryrun-test
```
