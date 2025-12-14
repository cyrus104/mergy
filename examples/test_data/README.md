# Mergy Test Data Structure

Minimal test set for validating Mergy functionality.

## Purpose

This directory contains a sample folder structure that demonstrates Mergy's matching and merging capabilities. Use it to:

- Verify installation is working correctly
- Test scanning and matching algorithms
- Practice merge operations safely
- Understand expected behavior before processing real data

## Directory Structure

```
computerNames/
├── computer-01/
│   └── data.txt              # Original content
├── computer-01-backup/
│   └── data.txt              # Different content (creates conflict)
├── computer-01.old/
│   └── data.txt              # Same as computer-01 (duplicate)
├── 192.168.1.5-computer02/
│   └── system.log            # Log entry 1
├── 192.168.1.5 computer02/
│   └── system.log            # Log entry 2 (different content)
└── unrelated-folder/
    └── other.txt             # Should not match any group
```

## Expanded Structure (Realistic Linux Workstation)

Each computer-01 variant now includes realistic Linux workstation files:

- **home/user/**: User home directory with dotfiles (.bash_history, .bashrc, .profile)
- **etc/**: System configuration files (hostname, network interfaces)
- **var/log/**: System logs (syslog, auth.log)
- **opt/**: Optional application data
- **tmp/**: Temporary files

### File Variety for Testing

| File Path | computer-01 | computer-01-backup | computer-01.old | Purpose |
|-----------|-------------|-------------------|-----------------|---------|
| `data.txt` | Original | Different | Identical | Conflict + Duplicate |
| `home/user/.bash_history` | Commands A | Commands B | Commands A | Conflict + Duplicate |
| `home/user/.bashrc` | Config | Identical | Identical | Deduplication |
| `home/user/Documents/notes.txt` | Notes v1 | Notes v2 | Notes v1 | Conflict + Duplicate |
| `home/user/Documents/report.pdf` | - | Unique | - | New file copy |
| `etc/hostname` | computer-01 | Identical | Identical | Deduplication |
| `var/log/syslog` | Logs A | Logs B | Logs C | Multiple conflicts |
| `opt/myapp/config.json` | Config A | Config B | Config A | Conflict + Duplicate |
| `opt/legacy/old_app.bin` | - | - | Unique | New file from old |
| `tmp/session.tmp` | - | Unique | - | New file copy |

This variety ensures comprehensive testing of:
- **Deduplication**: Identical files skipped (no copy needed)
- **Conflict Resolution**: Different files at same path (newer kept, older to .merged/)
- **New File Copying**: Unique files copied to primary folder

## Expected Matches

When running `mergy scan examples/test_data/computerNames`:

| Group | Folders | Match Type | Confidence |
|-------|---------|------------|------------|
| 1 | `computer-01`, `computer-01-backup`, `computer-01.old` | Exact prefix | 100% |
| 2 | `192.168.1.5-computer02`, `192.168.1.5 computer02` | Normalized | 90% |

The `unrelated-folder` should not match any group.

## Usage Instructions

```bash
# Scan test data
mergy scan examples/test_data/computerNames

# Dry-run merge (no file changes)
mergy merge examples/test_data/computerNames --dry-run

# Actual merge (creates .merged/ directories)
mergy merge examples/test_data/computerNames
```

## Expected Outcomes

### After Scan

- 2 match groups displayed above 70% threshold
- Group 1: 3 folders matching on "computer-01" base
- Group 2: 2 folders matching on "192.168.1.5-computer02" normalized name

### After Merge

For Group 1 (computer-01 variants):
- `data.txt` from `computer-01` and `computer-01.old` are identical (same SHA256)
- One copy kept, duplicate skipped
- `data.txt` from `computer-01-backup` has different content
- Conflict resolved: newer file kept, older moved to `.merged/` with hash suffix

For Group 2 (192.168.1.5 variants):
- `system.log` files have different content
- Conflict resolved: newer file kept, older moved to `.merged/` with hash suffix

### After Merge (Expanded Structure)

For Group 1 (computer-01 variants) with expanded structure:

**Deduplication (files skipped):**
- `.bashrc`, `.profile` - identical across all three
- `etc/hostname` - identical across all three
- `var/log/auth.log` - identical in computer-01 and computer-01-backup
- Multiple other identical files

**Conflicts Resolved:**
- `.bash_history` - different commands between computer-01 and computer-01-backup
- `Documents/notes.txt` - different content versions
- `var/log/syslog` - different log entries (timestamp-based resolution)
- `opt/myapp/config.json` - different configuration values
- Older versions moved to `.merged/` with hash suffix

**New Files Copied:**
- `Documents/report.pdf` from computer-01-backup
- `tmp/session.tmp` from computer-01-backup
- `opt/legacy/old_app.bin` from computer-01.old

**Result:** Primary folder contains all unique files, newest versions of conflicts, and no duplicates.

## Cleanup

To reset the test data after merging:

```bash
# Remove .merged directories
rm -rf examples/test_data/computerNames/*/.merged

# Verify cleanup
ls -la examples/test_data/computerNames/*/
```

To fully reset (restore original files if modified):

```bash
# Re-clone or restore from version control
git checkout -- examples/test_data/
```

## Notes

- This test data is intentionally minimal for quick validation
- For comprehensive testing, see `tests/manual_tui_testing.md`
- File timestamps may vary; conflict resolution depends on modification times
