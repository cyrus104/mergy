"""
Computer Data Organization Tool - CLI Interface (Legacy Shim).

This module is deprecated. Please use the installed `mergy` command or
import from the `mergy` package directly.

For backward compatibility, this module re-exports the CLI app from the
new package location so that `python mergy.py` continues to work.
"""

import warnings

warnings.warn(
    "Running 'python mergy.py' directly is deprecated. "
    "Please use the 'mergy' command after installation, or run 'python -m mergy'.",
    DeprecationWarning,
    stacklevel=2,
)

from mergy.cli import app, __version__

if __name__ == "__main__":
    app()
