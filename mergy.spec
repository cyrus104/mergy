# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Mergy - Computer Data Organization Tool

Build Instructions:
    # Install PyInstaller
    pip install pyinstaller

    # Build executable
    pyinstaller mergy.spec

    # Output location: dist/mergy (or dist/mergy.exe on Windows)

    # Test executable
    ./dist/mergy --version
    ./dist/mergy scan /path/to/test/data

Cross-Platform Testing Notes:
    - Linux: Test on Ubuntu 20.04+ and Fedora 35+
    - macOS: Test on macOS 11+ (Big Sur and later)
    - Windows: Test on Windows 10+ (64-bit)
    - Verify all dependencies bundle correctly (check dist/ size ~15-25 MB)
"""

import sys
from PyInstaller.utils.hooks import collect_submodules

# Collect all mergy submodules
mergy_hiddenimports = collect_submodules('mergy')

# Additional hidden imports for dependencies
additional_hiddenimports = [
    'typer',
    'typer.core',
    'typer.main',
    'rich',
    'rich.console',
    'rich.table',
    'rich.progress',
    'rich.panel',
    'rich.prompt',
    'rapidfuzz',
    'rapidfuzz.fuzz',
    'rapidfuzz.process',
    'click',
    'click.core',
]

# Combine all hidden imports
hiddenimports = mergy_hiddenimports + additional_hiddenimports

# Analysis configuration
a = Analysis(
    ['mergy.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude test frameworks and development tools
        'pytest',
        'pytest_cov',
        '_pytest',
        'coverage',
        'setuptools',
        'pip',
        'wheel',
        # Exclude unnecessary standard library modules
        'tkinter',
        'unittest',
        'doctest',
        'pdb',
        'profile',
        'pstats',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

# Create PYZ archive
pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=None,
)

# Create single-file executable
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='mergy',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,  # Strip debug symbols for smaller binary
    upx=True,    # Enable UPX compression (if available)
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # CLI application, not GUI
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # Icon can be added here if needed:
    # icon='path/to/icon.ico',  # Windows
    # icon='path/to/icon.icns', # macOS
)
