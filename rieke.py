#!/usr/bin/env python3
"""Portable setup/workspace/launch entry point; requires only Python's standard library."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent / 'python'))
from workspace_bootstrap import main
if __name__ == '__main__':
    raise SystemExit(main())
