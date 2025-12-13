"""Setup configuration for Mergy - Intelligent Folder Deduplication Tool."""

from setuptools import setup, find_packages
import os
import re

# Read requirements from requirements.txt
def read_requirements():
    """
    Load dependency specifications from the requirements.txt file located next to this module.
    
    Reads requirements.txt and returns a list of non-empty, non-comment lines with surrounding whitespace removed.
    
    Returns:
        list[str]: Requirement strings from requirements.txt (each line stripped), excluding empty lines and lines that begin with `#`.
    """
    requirements_path = os.path.join(os.path.dirname(__file__), "requirements.txt")
    with open(requirements_path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip() and not line.startswith("#")]

# Read long description from README.md
def read_readme():
    """
    Load the project's long description from a README.md file adjacent to this module.
    
    Returns:
        str: Contents of README.md as a string, or an empty string if the file does not exist.
    """
    readme_path = os.path.join(os.path.dirname(__file__), "README.md")
    if os.path.exists(readme_path):
        with open(readme_path, "r", encoding="utf-8") as f:
            return f.read()
    return ""


# Read version from mergy/cli.py (single source of truth)
def read_version():
    """
    Get the package version defined in mergy/cli.py.
    
    Searches mergy/cli.py for a top-level assignment to __version__ and returns the assigned string.
    
    Returns:
        version (str): The version string extracted from mergy/cli.py.
    
    Raises:
        RuntimeError: If no __version__ assignment is found in mergy/cli.py.
    """
    cli_path = os.path.join(os.path.dirname(__file__), "mergy", "cli.py")
    with open(cli_path, "r", encoding="utf-8") as f:
        content = f.read()
    match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)
    if match:
        return match.group(1)
    raise RuntimeError("Unable to find __version__ in mergy/cli.py")


setup(
    name="mergy",
    version=read_version(),
    description="Intelligent Folder Deduplication Tool with multi-tier matching and safe merging",
    long_description=read_readme(),
    long_description_content_type="text/markdown",
    author="Mergy Team",
    license="MIT",
    python_requires=">=3.9",
    install_requires=read_requirements(),
    packages=find_packages(exclude=["tests", "tests.*"]),
    py_modules=["merger_models", "merger_ops"],
    entry_points={
        "console_scripts": [
            "mergy=mergy.cli:app",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Intended Audience :: End Users/Desktop",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: System :: Filesystems",
        "Topic :: Utilities",
    ],
    keywords="folder deduplication merge fuzzy-matching file-management",
)