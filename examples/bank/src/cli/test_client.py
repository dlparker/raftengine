#!/usr/bin/env python
"""
Unified test client supporting multiple transports.
Works with both stub servers and raft clusters using the same transport.
"""
import asyncio
import argparse
from pathlib import Path
import sys

this_dir = Path(__file__).resolve().parent
for parent in this_dir.parents:
    if parent.name == 'src':
        if parent not in sys.path:
            sys.path.insert(0, str(parent))
            break
else:
    raise ImportError("Could not find 'src' directory in the path hierarchy")

from cli.test_client_common import validate, add_common_arguments

async def create_aiozmq_client(host, port):
    """Create aiozmq RPC client"""
    from tx_aiozmq.rpc_client import RPCClient
    return RPCClient(host, port)

async def create_grpc_client(host, port):
    """Create gRPC RPC client"""
    from tx_grpc.rpc_helper import RPCHelper
    uri = f"grpc://{host}:{port}"
    return await RPCHelper().rpc_client_maker(uri)

async def create_fastapi_client(host, port):
    """Create FastAPI RPC client"""
    from tx_fastapi.rpc_helper import RPCHelper
    uri = f"fastapi://{host}:{port}"
    return await RPCHelper().rpc_client_maker(uri)

async def create_astream_client(host, port):
    """Create AsyncStream RPC client"""
    from tx_astream.rpc_helper import RPCHelper
    uri = f"astream://{host}:{port}"
    return await RPCHelper().rpc_client_maker(uri)

async def main():
    parser = argparse.ArgumentParser(
        description='Unified Raft Banking Test Client',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --transport grpc demo --random
  %(prog)s --transport aiozmq test --loops 10 --json-output results.json
  %(prog)s --transport fastapi test --loops 5 --no-timing
  %(prog)s --transport grpc --port 8300 test --raft-stubs

Available transports:
  astream, aiozmq, fastapi, grpc
        """)
    
    parser.add_argument('--transport', '-t', 
                        choices=['astream', 'aiozmq', 'fastapi', 'grpc'],
                        required=True,
                        help='Transport mechanism to use')
    parser.add_argument('--host', type=str, default='localhost',
                        help='Host to connect to (default: localhost)')
    parser.add_argument('--port', '-p', type=int, default=None,
                        help='Port to connect to (overrides base-port calculation)')
    parser.add_argument('--base-port', '-b', type=int, default=50050,
                        help='Base port for transport offset calculation (default: 50050)')
    
    # Add common validation arguments
    add_common_arguments(parser)
    
    args = parser.parse_args()
    
    # Calculate port with transport offset (matching control_raft_server.py logic)
    if args.port is None:
        transport_offsets = {
            'astream': 0,
            'aiozmq': 100,
            'fastapi': 200,
            'grpc': 300
        }
        port = args.base_port + transport_offsets[args.transport]
    else:
        port = args.port
    
    print(f"Connecting to {args.transport} server at {args.host}:{port}")
    
    # Create the appropriate RPC client
    if args.transport == 'aiozmq':
        rpc_client = await create_aiozmq_client(args.host, port)
    elif args.transport == 'grpc':
        rpc_client = await create_grpc_client(args.host, port)
    elif args.transport == 'fastapi':
        rpc_client = await create_fastapi_client(args.host, port)
    elif args.transport == 'astream':
        rpc_client = await create_astream_client(args.host, port)
    else:
        raise ValueError(f"Unsupported transport: {args.transport}")
    
    # Update metadata to include transport information
    try:
        await validate(rpc_client, 
                      mode=args.mode,
                      loops=args.loops,
                      use_random_data=args.random,
                      print_timing=not args.no_timing,
                      json_output=args.json_output,
                      raft_stubs=args.raft_stubs)
    except Exception as e:
        print(f"Error during validation: {e}")
        sys.exit(1)
    
    print(f"Successfully completed {args.transport} validation")

if __name__ == "__main__":
    asyncio.run(main())
