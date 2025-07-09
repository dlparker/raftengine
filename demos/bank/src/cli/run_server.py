#!/usr/bin/env python
import asyncio
import argparse
import os
import sys
from pathlib import Path

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


async def main():
    parser = argparse.ArgumentParser(description='Banking Server Runner')
    # Define the list of valid choices

    VALID_TRANSPORTS = ['direct', 'async_streams', 'grpc']
    parser.add_argument(
        '-t', '--transport',  # Short and long option names
        required=True,   # Make the argument mandatory
        choices=VALID_TRANSPORTS,  # Restrict to this list
        help=f'Type of transport (must be one of: {", ".join(VALID_TRANSPORTS)})'
    )

    # Parse arguments
    args = parser.parse_args()
    if args.transport == "direct":
        print("For testing direct transport, just execute run_client.py, it creates server")
        raise SystemExit(0)

    
if __name__ == "__main__":
    asyncio.run(main())

