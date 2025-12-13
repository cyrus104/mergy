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
