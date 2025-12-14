# Mergy - Summary and Specification

## Executive Summary

Mergy is a Python-based CLI application designed to intelligently identify, analyze, and merge duplicate computer folders within a large collection (3000+ folders). It uses multi-tier fuzzy matching algorithms to detect folders that represent the same device (e.g., "135897-ntp" and "135897-ntp.newspace"), provides an interactive TUI for user decision-making, and safely merges data while preserving all file versions through a conflict resolution system.

**Key Features:**
- Multi-tier folder matching (exact prefix, normalized, token-based, fuzzy)
- Interactive terminal UI for merge selection
- Safe merging with no data loss (conflicts moved to permanent `.merged/` archives, never auto-deleted)
- SHA256-based file comparison and deduplication
- Dry-run mode for testing
- Comprehensive logging of all operations
- Progress tracking for large-scale operations

---

## Technical Specification

### 1. System Requirements

**Environment:**
- Python 3.11 or higher
- Operating System: Linux, macOS, or Windows
- Disk space: Sufficient for log files (typically <100MB)

**Dependencies:**
```
typer[all]>=0.9.0    # CLI framework with rich support
rich>=13.0.0         # Terminal UI and formatting
rapidfuzz>=3.0.0     # Fast fuzzy string matching
```

**Installation:**
```bash
pip install typer[all] rich rapidfuzz
```

---

### 2. Application Architecture

**File Structure:**
```
mergy/                              # Root project directory
├── mergy.py                        # Main CLI application (Typer app)
├── setup.py                        # Package installation configuration
├── requirements.txt                # Python dependencies
├── pytest.ini                      # Pytest configuration
├── README.md                       # User documentation
├── AGENTS.md                       # Technical specification (this file)
├── LICENSE                         # MIT license
├── mergy/                          # Main package
│   ├── models/                     # Data models package
│   │   ├── match_reason.py         # MatchReason enum
│   │   └── data_models.py          # ComputerFolder, FolderMatch, MergeSelection, etc.
│   ├── matching/                   # Folder matching package
│   │   └── folder_matcher.py       # FolderMatcher class (multi-tier algorithm)
│   ├── scanning/                   # File scanning package
│   │   ├── file_hasher.py          # FileHasher class (SHA256 hashing)
│   │   └── folder_scanner.py       # FolderScanner class (metadata collection)
│   ├── operations/                 # File operations package
│   │   └── file_operations.py      # FileOperations class (copy, move, conflict resolution)
│   ├── ui/                         # User interface package
│   │   └── merge_tui.py            # MergeTUI class (Rich-based interactive UI)
│   └── orchestration/              # Workflow orchestration package
│       ├── merge_orchestrator.py   # MergeOrchestrator class (main workflow)
│       └── merge_logger.py         # MergeLogger class (structured logging)
```

**Module Responsibilities:**

| Module/Package | Classes/Components | Purpose |
|----------------|-------------------|---------|
| `mergy.models` | `ComputerFolder`, `FolderMatch`, `MergeSelection`, `FileConflict`, `MergeOperation`, `MergeSummary`, `MatchReason` | Core data structures and enums |
| `mergy.matching` | `FolderMatcher` | Multi-tier folder matching algorithm |
| `mergy.scanning` | `FileHasher`, `FolderScanner` | File hashing and metadata collection |
| `mergy.operations` | `FileOperations` | File system operations (copy, move, conflict resolution) |
| `mergy.ui` | `MergeTUI` | Rich-based terminal user interface |
| `mergy.orchestration` | `MergeOrchestrator`, `MergeLogger` | Workflow coordination and structured logging |
| `mergy.py` | Typer CLI app | Command-line interface and entry point |

---

### 3. Core Algorithms

#### 3.1 Multi-Tier Folder Matching

The matching algorithm operates in four tiers, from highest to lowest confidence:

**Tier 1: Exact Prefix Match (100% confidence)**
- Detects when one folder name is an exact prefix of another
- Example: `"135897-ntp"` matches `"135897-ntp.newspace"`
- Implementation: String prefix check with delimiter validation

**Tier 2: Normalized Match (90% confidence)**
- Normalizes folder names by replacing delimiters (-, _, ., space)
- Example: `"192.168.1.5-computer01"` matches `"192.168.1.5 computer01"`
- Implementation: Regex-based normalization + string comparison

**Tier 3: Token Match (70% confidence, scaled by similarity)**
- Extracts tokens (words) and compares using Jaccard similarity
- Example: `"computer01"` matches `"192.168.1.5-computer01"`
- Implementation: Token extraction + set intersection/union ratio

**Tier 4: Fuzzy Match (50% confidence, scaled by similarity)**
- Uses Levenshtein distance for spelling variations
- Example: `"comptuer01"` matches `"computer01"`
- Implementation: RapidFuzz token_sort_ratio

**Confidence Threshold:**
- Default: 70% (configurable via `--min-confidence`)
- Only matches above threshold are presented to user

#### 3.2 File Conflict Resolution

**Conflict Detection:**
1. Compare files at same relative path in different folders
2. Calculate SHA256 hash for each file
3. If hashes differ → conflict detected
4. If hashes match → skip (deduplicate)

**Conflict Resolution Strategy:**
1. Compare file creation timestamps (`st_ctime`)
2. Keep newer file in primary location
3. Move older file to `.merged/` subfolder at same directory level
4. Rename older file: `originalname_hash16chars.ext`

**Example:**
```
Primary:   /computers/135897-ntp.newspace/logs/system.log (2024-01-15, abc123...)
Merge-from: /computers/135897-ntp/logs/system.log (2024-01-10, def456...)

Result:
  Keep:     /computers/135897-ntp.newspace/logs/system.log (newer)
  Move to:  /computers/135897-ntp.newspace/logs/.merged/system.log_def456789abcdef1.log
```

---

### 4. User Workflows

#### 4.1 Scan Workflow (Read-Only)

```bash
python mergy.py scan /path/to/computerNames [--min-confidence 70]
```

**Steps:**
1. Scan all immediate subdirectories
2. Collect metadata (file count, size, date ranges)
3. Apply matching algorithm
4. Display matches above confidence threshold
5. Generate log file with findings

**Output:**
- Console: Summary table of matches
- Log file: Detailed match information with confidence scores

#### 4.2 Merge Workflow (Interactive)

```bash
python mergy.py merge /path/to/computerNames [--dry-run] [--min-confidence 70]
```

**Steps:**
1. **Scan Phase:** Same as scan workflow
2. **Interactive Selection Phase:**
   - For each match group (with progress bar):
     - Display folders in group
     - User actions: (m)erge, (s)kip, (q)uit
     - If merge selected:
       - User selects which folders to merge (1 2 3 or "all")
       - User selects primary folder
       - User confirms merge
3. **Analysis Phase:**
   - For each selected merge:
     - Compare file trees
     - Identify new files, duplicates, and conflicts
     - Display summary
4. **Execution Phase:**
   - Copy new files to primary
   - Resolve conflicts (move older to .merged/)
   - Skip duplicate files
   - Remove empty directories
5. **Summary Phase:**
   - Display overall statistics
   - Generate comprehensive log

**Progress Tracking:**
- Match group review: `[████████░░░░] 5/47 match groups`
- File operations: `[████████████] Merging folder-name... 85%`

---

### 5. Data Models

#### 5.1 Core Data Structures

```python
@dataclass
class ComputerFolder:
    path: Path                        # Full path to folder
    name: str                         # Folder name
    file_count: int                   # Total files
    total_size: int                   # Total bytes
    oldest_file_date: datetime        # Earliest file creation
    newest_file_date: datetime        # Latest file creation

@dataclass
class FolderMatch:
    folders: List[ComputerFolder]     # Matched folders
    confidence: float                 # Match confidence (0-100)
    match_reason: MatchReason         # Which tier matched
    base_name: str                    # Common base name

@dataclass
class MergeSelection:
    primary: ComputerFolder           # Destination folder
    merge_from: List[ComputerFolder]  # Source folders
    match_group: FolderMatch          # Original match

@dataclass
class FileConflict:
    relative_path: Path               # Path within folder
    primary_file: Path                # Primary file location
    conflicting_file: Path            # Conflicting file location
    primary_hash: str                 # SHA256 of primary
    conflict_hash: str                # SHA256 of conflict
    primary_ctime: datetime           # Primary creation time
    conflict_ctime: datetime          # Conflict creation time

@dataclass
class MergeOperation:
    selection: MergeSelection         # User selection
    dry_run: bool                     # Dry run mode flag
    timestamp: datetime               # Operation start time
    files_copied: int                 # New files copied
    files_skipped: int                # Duplicate files skipped
    conflicts_resolved: int           # Conflicts handled
    folders_removed: int              # Empty folders cleaned
    errors: List[str]                 # Error messages
```

---

### 6. Command-Line Interface

#### 6.1 Commands

**scan** - Analyze folders without modification
```bash
python mergy.py scan PATH [OPTIONS]

Arguments:
  PATH    Path to computerNames directory [required]

Options:
  --min-confidence, -c FLOAT    Minimum match confidence (0-100) [default: 70]
  --log-file, -l PATH           Custom log file location
  --verbose, -V                 Enable verbose console output
  --help                        Show help message
```

**merge** - Interactive merge process
```bash
python mergy.py merge PATH [OPTIONS]

Arguments:
  PATH    Path to computerNames directory [required]

Options:
  --min-confidence, -c FLOAT    Minimum match confidence (0-100) [default: 70]
  --dry-run, -n                 Simulate merge without changes
  --log-file, -l PATH           Custom log file location
  --verbose, -V                 Enable verbose console output
  --help                        Show help message
```

**Global Options:**
```bash
--version, -v    Show version and exit (note: -V is used for verbose to avoid conflict)
```

---

### 7. Logging System

#### 7.1 Log File Format

**Filename:** `merge_log_YYYY-MM-DD_HH-MM-SS.log`  
**Location:** Current working directory (not in computerNames)

**Structure:**
```
=================================================================
Computer Data Organization Tool - Merge Log
=================================================================
Timestamp: 2024-01-15 14:30:00
Mode: LIVE MERGE / DRY RUN

=================================================================
SCAN PHASE
=================================================================
Base Path: /path/to/computerNames
Minimum Confidence Threshold: 70%
Total folders scanned: 3000
Match groups found: 47
Match groups above threshold: 32

Match Groups:
  Group 1: (95% - exact_prefix)
    - 135897-ntp
    - 135897-ntp.newspace
  ...

=================================================================
MERGE PHASE
=================================================================

Selection 1:
  Confidence: 95%
  Primary: 135897-ntp.newspace
  Merging from:
    - 135897-ntp
    - 135897_ntp_backup

[2024-01-15 14:35:12] Starting merge into: 135897-ntp.newspace
  Merging: 135897-ntp
  Files copied: 45
  Files skipped (duplicates): 120
  Conflicts resolved: 8
  Empty folders removed: 3
[2024-01-15 14:35:45] Completed merge

...

=================================================================
SUMMARY
=================================================================
Total merge operations: 5
Files copied: 1,234
Files skipped (duplicates): 567
Conflicts resolved: 89
Empty folders removed: 5
Duration: 5m 23s

Log file: /current/dir/merge_log_2024-01-15_14-30-00.log
=================================================================
```

---

### 8. Error Handling

#### 8.1 Error Categories

**File System Errors:**
- Permission denied → Skip file, log warning
- File not found → Log error, continue
- Disk full → Abort operation, log error

**Hash Calculation Errors:**
- Unable to read file → Log error, skip file
- Corrupted file → Log error, skip file

**User Input Errors:**
- Invalid folder selection → Re-prompt user
- Invalid primary selection → Re-prompt user

**Critical Errors:**
- Base path doesn't exist → Exit with error message
- Base path not a directory → Exit with error message

#### 8.2 Error Recovery

- Non-critical errors are logged and operation continues
- Critical errors abort the current operation
- All errors are recorded in log file
- Error summary displayed at end of operation

---

### 9. Safety Features

#### 9.1 Data Protection

**No Deletions:**
- Original files are never deleted during merge
- Older files are moved to **permanent** `.merged/` archives with SHA256 hash suffix
- `.merged/` directories are **never automatically deleted** by Mergy—they are preserved indefinitely as safety archives
- Empty directories removed only after successful merge (but `.merged/` directories are always preserved)

**No Overwrites:**
- Newer files always take precedence
- Older files preserved in `.merged/` directory indefinitely
- Identical files (by hash) are safely skipped

**User-Controlled Cleanup:**
- Manual cleanup of `.merged/` directories is **optional** and should only be done after thorough verification
- Minimum recommended retention: 30-90 days (longer for critical data)
- See README.md "Advanced: .merged Directory Cleanup" for safe cleanup procedures

**Dry Run Mode:**
- Full simulation of merge process
- No file system modifications
- Complete logging of what would happen
- Enables safe testing before actual merge

#### 9.2 Verification

**File Integrity:**
- SHA256 hashing ensures accurate comparison
- Creation timestamp comparison for conflict resolution
- Hash caching for performance on repeated operations

**Operation Tracking:**
- Every file operation logged
- Timestamps recorded for all operations
- Error tracking with detailed messages
- Summary statistics for verification

---

### 10. Performance Characteristics

#### 10.1 Expected Performance

**Scanning:**
- ~3000 folders: 2-5 minutes (depending on file count)
- Metadata collection: ~10-20 files/second
- No file content reading during scan

**Matching:**
- ~3000 folders: <10 seconds
- O(n²) worst case, optimized with early exits
- Typically finds 30-50 match groups

**Merging:**
- Depends on file count and size
- Hashing: ~50-100 MB/second
- Copying: Limited by disk I/O
- Typical merge: 1-5 minutes per folder pair

#### 10.2 Optimization Strategies

**Hash Caching:**
- In-memory cache of file hashes
- Prevents redundant calculations
- Significant speedup for duplicate detection

**Incremental Processing:**
- User reviews matches one at a time
- Can quit and resume (no state persistence)
- Progress tracking for user feedback

**Selective Scanning:**
- Only scans immediate subdirectories
- Skips `.merged` directories during walks
- Follows symlinks (configurable behavior)

---

### 11. Limitations and Constraints

#### 11.1 Current Limitations

**Scale:**
- Designed for ~3000 folders
- No parallelization (sequential processing)
- Memory usage scales with file count

**Matching:**
- No machine learning or advanced NLP
- Relies on name similarity only
- May produce false positives at low confidence

**State:**
- No persistence between runs
- Cannot resume interrupted operations
- Must complete match review in one session

**File System:**
- Creation time used (not birth time on all platforms)
- Symlinks followed (potential for loops)
- No special handling for hardlinks

#### 11.2 Known Issues

- Very long folder names may cause display issues in TUI
- Large files (>1GB) may slow hash calculation
- Network drives may have performance issues
- Windows path length limitations may apply

---

### 12. Future Enhancements

#### 12.1 Potential Features

**Phase 2:**
- State persistence (save/resume sessions)
- Undo capability (transaction log)
- Batch mode (apply rules automatically)
- Configuration file support (.computer-org.yaml)

**Phase 3:**
- Parallel scanning and hashing
- Web-based UI alternative
- Advanced analytics and reporting
- Export to CSV/JSON formats

**Phase 4:**
- Machine learning for better matching
- Automated merge recommendations
- Integration with backup systems
- Network folder support optimization

---

### 13. Testing Strategy

#### 13.1 Test Coverage

**Unit Tests:**
- Matcher algorithms (all four tiers)
- File hasher with various file sizes
- Conflict resolution logic
- Data model validation

**Integration Tests:**
- Scanner with test directory structure
- File operations with temp directories
- End-to-end merge workflow
- Dry-run mode verification

**Manual Tests:**
- TUI interaction and edge cases (see `tests/manual_tui_testing.md`)
- Large-scale operations (1000+ folders)
- Error handling and recovery
- Cross-platform compatibility

#### 13.2 Test Data

**Minimal Test Set:**
```
test_data/
├── computer-01/
├── computer-01-backup/
├── computer-01.old/
├── 192.168.1.5-computer02/
├── 192.168.1.5 computer02/
└── unrelated-folder/
```

**Expected Matches:**
- Group 1: computer-01, computer-01-backup, computer-01.old (exact prefix)
- Group 2: 192.168.1.5-computer02, 192.168.1.5 computer02 (normalized)

---

### 14. Deployment

#### 14.1 Installation Methods

**Method 1: Direct Execution**
```bash
# Install dependencies (via requirements.txt or manually)
pip install -r requirements.txt
# Or: pip install typer[all] rich rapidfuzz

# Run scan (read-only analysis)
python mergy.py scan /path/to/data

# Run merge (interactive)
python mergy.py merge /path/to/data
```

**Method 2: Package Installation (Recommended)**
```bash
# Install as package
pip install -e .

# Run as command
mergy scan /path/to/data
mergy merge /path/to/data
```

**Method 3: Standalone Executable**
```bash
# Install PyInstaller
pip install pyinstaller

# Build executable using spec file
pyinstaller mergy.spec

# Run executable
./dist/mergy scan /path/to/data
./dist/mergy merge /path/to/data
```

---

### 15. Support and Maintenance

#### 15.1 Troubleshooting

**Common Issues:**

| Issue | Solution |
|-------|----------|
| "Base path does not exist" | Verify path and permissions |
| No matches found | Lower --min-confidence threshold |
| Permission denied errors | Run with appropriate user permissions |
| Slow performance | Check disk I/O, reduce file count |
| Memory issues | Process folders in smaller batches |

#### 15.2 Maintenance Tasks

**Regular:**
- Review log files for errors
- Monitor disk space for `.merged/` directories (expected to grow over time)
- Archive old log files

**Periodic:**
- Update dependencies (pip install --upgrade)
- Review and adjust confidence thresholds

**Optional (User-Controlled):**
- `.merged/` directory cleanup is **optional** and requires manual execution
- Mergy **never automatically deletes** `.merged/` directories
- Minimum retention: 30-90 days (longer for critical/irreplaceable data)
- Before cleanup: verify data, create external archives, document deletion
- See README.md "Advanced: .merged Directory Cleanup" section for safe procedures

---

## Appendix A: File Format Examples

### A.1 Merged Directory Structure

```
135897-ntp.newspace/
├── data/
│   ├── inventory.xml
│   └── config.json
├── logs/
│   ├── system.log
│   └── .merged/
│       ├── system.log_abc123def4567890  # Older version with hash
│       └── app.log_fedcba9876543210     # Another older version
└── temp/
    └── cache.db
```

### A.2 Example Log Entries

```
[2024-01-15 14:35:13] Starting merge into: 135897-ntp.newspace
  Merging: 135897-ntp
  Files copied: 45
  Files skipped (duplicates): 120
  Conflicts resolved: 8
    ! Conflict: logs/system.log - kept newer, moved older to .merged/system.log_abc123def4567890
    ! Conflict: data/report.csv - kept newer, moved older to .merged/report.csv_fedcba9876543210
  Empty folders removed: 3
[2024-01-15 14:35:45] Completed merge
```

---

## Appendix B: Glossary

| Term | Definition |
|------|------------|
| **Primary Folder** | The destination folder where all data will be merged into |
| **Merge-from Folder** | Source folder(s) that will be merged into the primary |
| **Confidence Score** | Percentage indicating how likely two folders represent the same device (0-100%) |
| **Match Group** | Collection of 2+ folders identified as potential duplicates |
| **Conflict** | Two files at the same path with different content (different hashes) |
| **Duplicate** | Two files at the same path with identical content (same hash) |
| **.merged Directory** | Permanent safety archive created at each level to store older versions of conflicting files (never auto-deleted by Mergy) |
| **Dry Run** | Simulation mode that performs all analysis without modifying files |
| **Hash Suffix** | First 16 characters of SHA256 hash appended to filename |
| **Creation Time** | File's st_ctime value used for determining which file is newer |
