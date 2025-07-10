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
from cli.setup_configs import (
    setup_configs, get_available_steps, get_available_transports, 
    get_module_path, validate_step_transport
)
from base.test_banking import test_banking


async def main_async(args=None):
    """Main async function that can be called directly or from command line"""
    parser = argparse.ArgumentParser(
        description='Banking Server Client Validator',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --step step1 --transport direct --database mybank.db
  %(prog)s --step step2 --transport grpc --port 8080
  %(prog)s -s step2 -t fastapi -p 8000

Available step/transport combinations:
  step1: direct (in-process, uses database file)
  step2: aiozmq, grpc, fastapi (network client-server, uses port)
        """
    )

    # Step and transport arguments
    parser.add_argument(
        '-s', '--step', 
        required=True,
        choices=get_available_steps(),
        help='Demo evolution step (step1=direct, step2=client-server)'
    )
    parser.add_argument(
        '-t', '--transport',
        required=True,
        help='Transport mechanism within the step'
    )
    
    parser.add_argument('--database', '-d', 
                       default='banking_direct.db',
                       help='Database file path (used with step1/direct)')
    parser.add_argument('-p', '--port', type=int, 
                       help='Server port number (required for step2 transports)')
    

    # Parse arguments
    if args is None:
        parsed_args = parser.parse_args()
    else:
        parsed_args = parser.parse_args(args)

    # Get step and transport
    step = parsed_args.step
    transport = parsed_args.transport
    if parsed_args.transport != "direct":
        if not parsed_args.port:
            parser.error("--port is required for non-direct")
    
    # Validate combination
    valid, message = validate_step_transport(step, transport)
    if not valid:
        parser.error(message)

    # Get module and create client
    module_path = get_module_path(step, transport)
    module = importlib.import_module(module_path)
    SetupHelper = getattr(module, "SetupHelper")
    helper = SetupHelper()
    
    if parsed_args.transport == "direct":
        client = await helper.get_client(db_file=Path(parsed_args.database))
    else:
        client = await helper.get_client(host='localhost', port=parsed_args.port)
    
    await test_banking(client)

def main():
    """Entry point for command line usage"""
    asyncio.run(main_async())

if __name__ == "__main__":
    main()

