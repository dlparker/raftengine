#!/usr/bin/env python
import asyncio
import argparse
import os
import sys
from pathlib import Path
this_dir = Path(__file__).resolve().parent
for parent in this_dir.parents:
    if parent.name == 'src':
        if parent not in sys.path:
            sys.path.insert(0, str(parent))
            break
else:
    raise ImportError("Could not find 'src' directory in the path hierarchy")
from raft_ops.server_main import main_async

def main():
    """Entry point for command line usage"""
    asyncio.run(main_async())
    
if __name__ == "__main__":
    main()

