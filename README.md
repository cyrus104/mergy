# Mergy - Computer Data Organization Tool

Intelligent folder merging CLI for duplicate computer backups.

![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![License MIT](https://img.shields.io/badge/license-MIT-green)
![Status Alpha](https://img.shields.io/badge/status-alpha-orange)

**Quick Links:** [Installation](#installation) | [Quick Start](#quick-start) | [Usage](#usage-examples) | [Features](#features) | [Troubleshooting](#troubleshooting)

## Features

- **Multi-tier folder matching** - Exact prefix, normalized, token-based, and fuzzy matching with confidence scoring
- **Interactive Rich-based TUI** - Terminal user interface for merge selection and progress tracking
- **Safe merging with no data loss** - Conflicts moved to `.merged/` with hash suffixes
- **SHA256-based file comparison** - Accurate deduplication through content hashing
- **Dry-run mode** - Test operations without file system changes
- **Comprehensive structured logging** - Timestamped logs for audit trails
- **Cross-platform support** - Linux, macOS, and Windows

## Installation

### Method 1: Package Installation (Recommended)

```bash
pip install -e .
mergy --version
```

### Method 2: Direct Execution

```bash
pip install -r requirements.txt
python mergy.py --version
```

### Method 3: Standalone Executable

```bash
# Install PyInstaller
pip install pyinstaller

# Build executable
pyinstaller mergy.spec

# Run executable
./dist/mergy --version
```

### Requirements

- Python 3.11+
- Dependencies: typer, rich, rapidfuzz (see `requirements.txt`)

## Quick Start

1. **Scan folders to identify duplicates:**
   ```bash
   mergy scan /path/to/computerNames
   ```

2. **Review matches** in the output table with confidence scores

3. **Test merge with dry-run:**
   ```bash
   mergy merge /path/to/computerNames --dry-run
   ```

4. **Perform actual merge:**
   ```bash
   mergy merge /path/to/computerNames
   ```

5. **Review log file** `merge_log_YYYY-MM-DD_HH-MM-SS.log` for details

## Usage Examples

```bash
# Basic scan
mergy scan /path/to/computerNames

# Scan with lower confidence threshold
mergy scan /path/to/computerNames --min-confidence 50

# Dry-run merge (no file changes)
mergy merge /path/to/computerNames --dry-run

# Merge with custom log file
mergy merge /path/to/computerNames --log-file ~/merge-2024.log

# Verbose output for debugging
mergy merge /path/to/computerNames --verbose

# Show version
mergy --version
```

## Command Reference

| Command | Options | Description |
|---------|---------|-------------|
| `scan PATH` | `--min-confidence`, `--log-file`, `--verbose` | Analyze folders without modification |
| `merge PATH` | `--min-confidence`, `--dry-run`, `--log-file`, `--verbose` | Interactive merge process |

## Configuration Options

| Option | Description | Default |
|--------|-------------|---------|
| `--min-confidence` | Threshold for displaying matches (0-100) | 70 |
| `--dry-run` | Simulate merge without file system changes | False |
| `--log-file PATH` | Custom log file location | `merge_log_YYYY-MM-DD_HH-MM-SS.log` |
| `--verbose` | Enable detailed console output | False |

## Best Practices

- **Always run `scan` first** to understand matches before merging
- **Use `--dry-run`** to preview changes before actual merge
- **Start with default confidence (70%)** and adjust if needed:
  - Lower (50-60) for more matches
  - Higher (80-90) for precision
- **Review log files** after operations for detailed audit trail
- **Keep `.merged/` directories** until confident older versions aren't needed
- **Test on small subset** before processing large folder collections
- **Ensure sufficient disk space** (merging doesn't delete originals immediately)

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Base path does not exist" | Verify path spelling and permissions with `ls -la` |
| No matches found | Lower `--min-confidence` threshold (try 50-60) or check folder naming patterns |
| Permission denied errors | Run with appropriate user permissions or use `sudo` (caution advised) |
| Slow performance | Check disk I/O with `iostat`, reduce file count per operation, or use SSD |
| Memory issues | Process folders in smaller batches, close other applications |
| Long folder names display issues | Terminal width <80 columns may truncate; resize or use `--verbose` for full paths |
| Hash calculation errors | Check file permissions and disk health; corrupted files are skipped and logged |

## How It Works

### Four-Tier Matching Algorithm

1. **Exact Prefix Match** - Folders starting with identical base name (e.g., `computer-01`, `computer-01-backup`)
2. **Normalized Match** - After removing common suffixes and normalizing separators
3. **Token-Based Match** - Matching significant tokens within folder names
4. **Fuzzy Match** - String similarity for catching variations

### Conflict Resolution

- **Keep newer file** based on modification time
- **Move older file** to `.merged/` subdirectory with 16-character hash suffix
- **Skip duplicates** when SHA256 hashes match (identical content)

### Interactive Workflow

1. Scan folders for matches
2. Review match groups with confidence scores
3. Select folders to merge
4. Choose primary folder (merge target)
5. Confirm operation
6. Execute merge with progress tracking
7. View summary of operations

## Known Limitations

- Designed for ~3000 folders; sequential processing (no parallelization)
- No state persistence between runs; cannot resume interrupted operations
- Creation time (`st_ctime`) used for conflict resolution (not birth time on all platforms)
- Symlinks are followed (potential for loops if circular)
- Very long folder names (>60 chars) may truncate in TUI display
- Large files (>1GB) may slow hash calculation
- Network drives may have performance issues

## Maintenance Tasks

### Regular Tasks

```bash
# Review log files
ls -lh merge_log_*.log

# Monitor disk space for .merged directories
du -sh /path/to/computerNames/*/.merged

# Archive old log files
gzip merge_log_*.log
mv *.gz logs/archive/

# Clean up .merged directories after verification (CAUTION: irreversible)
find /path/to/computerNames -type d -name ".merged" -exec rm -rf {} +
```

### Periodic Tasks

- Update dependencies: `pip install --upgrade typer rich rapidfuzz`
- Review and adjust confidence thresholds based on false positive/negative rates
- Test on sample data before large operations: use `examples/test_data/`
- Verify Python version compatibility: `python --version` (ensure 3.11+)

### Backup Recommendations

- Always maintain backups before merging large datasets
- Test merge operations on copies first
- Keep `.merged/` directories until confident older versions aren't needed (typically 30-90 days)
- Archive log files for audit trail (recommend 1 year retention)

## Development

### Setup

```bash
# Clone repository
git clone <repository-url>
cd mergy

# Install in editable mode with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run tests with coverage
pytest --cov=mergy --cov-report=html
open htmlcov/index.html
```

### Project Structure

- `mergy/models/` - Data models and enums (`ComputerFolder`, `FolderMatch`, etc.)
- `mergy/matching/` - Multi-tier folder matching algorithm
- `mergy/scanning/` - File hashing and metadata collection
- `mergy/operations/` - File system operations (copy, move, conflict resolution)
- `mergy/ui/` - Rich-based terminal user interface
- `mergy/orchestration/` - Workflow coordination and logging
- `mergy.py` - CLI entry point (re-exports from `mergy.cli`)
- `tests/` - Comprehensive test suite with unit, integration, and manual tests

### Testing

```bash
# Unit tests
pytest tests/test_*.py -k "not integration"

# Integration tests
pytest tests/test_*_integration.py

# Manual TUI tests
# Follow tests/manual_tui_testing.md

# Test coverage target: >90% for core modules
pytest --cov=mergy --cov-report=term-missing
```

### Code Organization

- Each package has `__init__.py` exporting public API
- Data models are immutable dataclasses with type hints
- All file operations use `pathlib.Path` for cross-platform compatibility
- Error handling: non-critical errors logged, critical errors abort

## Building Executables

### Prerequisites

```bash
pip install pyinstaller
```

### Build Process

```bash
# Build standalone executable
pyinstaller mergy.spec

# Output location
ls -lh dist/mergy      # Linux/macOS
dir dist\mergy.exe     # Windows
```

### Distribution

- Executable size: ~15-25 MB (includes Python runtime and dependencies)
- No Python installation required on target system
- Distribute `dist/mergy` (or `dist/mergy.exe`) as single file
- Include `README.md` and `LICENSE` with distribution

### Platform-Specific Notes

- **Linux**: Executable may require `chmod +x dist/mergy` on some systems
- **macOS**: May require code signing for distribution (see Apple Developer docs)
- **Windows**: Antivirus software may flag PyInstaller executables (false positive); consider code signing

### Testing Executables

```bash
# Verify version
./dist/mergy --version

# Test scan
./dist/mergy scan examples/test_data/computerNames

# Test dry-run merge
./dist/mergy merge examples/test_data/computerNames --dry-run
```

## Project References

- [AGENTS.md](AGENTS.md) - Full technical specification
- [tests/manual_tui_testing.md](tests/manual_tui_testing.md) - Manual testing scenarios
- [LICENSE](LICENSE) - MIT license details

## License

MIT License - see [LICENSE](LICENSE) for full text.

Copyright (c) 2025 cyrus104

## Support

- For bugs or feature requests, refer to the project repository
- For technical details, see [AGENTS.md](AGENTS.md) specification
