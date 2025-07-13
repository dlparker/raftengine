#!/usr/bin/env python
import asyncio
import argparse
import os
import sys
from pathlib import Path
import importlib

# Dynamically find the 'src' directory relative to this script
script_dir = Path(__file__).resolve().parent
src_dir = None
for parent in script_dir.parents:
    if parent.name == 'src':
        src_dir = parent
        break
else:
    raise ImportError("Could not find 'src' directory in the path hierarchy")

# Add the 'src' directory to sys.path if not already present
if src_dir not in sys.path:
    sys.path.insert(0, str(src_dir))

from step5.raft_ops.server_main import main_async

def main():
    """Entry point for command line usage"""
    asyncio.run(main_async())
    
if __name__ == "__main__":
    main()

