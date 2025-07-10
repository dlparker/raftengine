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

async def start_server(step, transport, db_file, port=None, uri=None):
    """Start a server with the given step/transport configuration"""
    module_path = get_module_path(step, transport)
    module = importlib.import_module(module_path)
    SetupHelper = getattr(module, "SetupHelper")
    helper = SetupHelper()
    server = await helper.get_server(db_file=Path(db_file), port=port)
    await helper.serve(server=server)

async def main_async(args=None):
    """Main async function that can be called directly or from command line"""
    parser = argparse.ArgumentParser(
        description='Banking Server Runner',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --step step2 --transport grpc --port 8080
  %(prog)s -s step2 -t fastapi -p 8000

Available step/transport combinations:
  step1: direct (not applicable - server created by client automatically)
  step2: aiozmq, grpc, fastapi (network servers that need explicit startup)
        """
    )

    # Step and transport arguments
    parser.add_argument(
        '-s', '--step',
        required=True,
        choices=get_available_steps(),
        help='Demo evolution step (only step2 applicable for servers)'
    )
    parser.add_argument(
        '-t', '--transport',
        required=True,
        help='Transport mechanism within the step'
    )
    
    parser.add_argument('--database', '-d', 
                        default='banking_direct.db',
                        help='Database file path (default: banking_direct.db)')
    
    parser.add_argument('-u', '--uri', type=int, help='Uri from cluster node list')
    parser.add_argument('-p', '--port', type=int, help='Server port number (required if not -u)')

    # Parse arguments
    if args is None:
        parsed_args = parser.parse_args()
    else:
        parsed_args = parser.parse_args(args)

    # Get step and transport
    step = parsed_args.step
    transport = parsed_args.transport
    
    # Validate combination
    valid, message = validate_step_transport(step, transport)
    if not valid:
        parser.error(message)
        
    if step == "step1":
        print("For step1/direct, just execute run_client.py - it creates the server automatically")
        print("Step1 uses in-process direct calls, no separate server needed.")
        raise SystemExit(0)

    if parsed_args.port is None and parsed_args.uri is None:
        parser.error('step2 transports require either --port or --uri')

    await start_server(step, transport, parsed_args.database, parsed_args.port, parsed_args.uri)

def main():
    """Entry point for command line usage"""
    asyncio.run(main_async())
    
if __name__ == "__main__":
    main()

