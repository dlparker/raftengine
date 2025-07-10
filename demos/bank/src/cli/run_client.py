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
from cli.transports import transport_table
from base.test_banking import test_banking

async def main():
    parser = argparse.ArgumentParser(description='Banking Server Client Validator')
    # Define the list of valid choices

    valid_transports = list(transport_table.keys())
    parser.add_argument(
        '-t', '--transport',  # Short and long option names
        required=True,   # Make the argument mandatory
        choices=valid_transports,  # Restrict to this list
        help=f'Type of transport (must be one of: {", ".join(valid_transports)})'
    )
    parser.add_argument('--database', '-d', 
                       default='banking_direct.db',
                       help='ONLY WITH -t direct! Database file path (default: banking_direct.db)')
    parser.add_argument('-p', '--port', type=int, help='Server Port Number (required if not -u, not used for direct)')
    

    # Parse arguments
    args = parser.parse_args()

    module_path = transport_table[args.transport]
    module = importlib.import_module(module_path)
    SetupHelper = getattr(module, "SetupHelper")
    helper = SetupHelper()
    if args.transport == "direct":
        client = await helper.get_client(db_file=Path(args.database))
    else:
        client = await helper.get_client(host='localhost', port=args.port)
    await test_banking(client)
        
    
        

    
if __name__ == "__main__":
    asyncio.run(main())

