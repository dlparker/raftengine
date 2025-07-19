#!/usr/bin/env python
"""
Unified stub server supporting multiple transports.
Works with both stub clients and raft clusters using the same transport.
"""
import asyncio
import argparse
from pathlib import Path
import sys
from raftengine.deck.log_control import LogController
# setup LogControl before importing any modules that might initialize it first
LogController.controller = None
log_control = LogController.make_controller()

this_dir = Path(__file__).resolve().parent
for parent in this_dir.parents:
    if parent.name == 'src':
        if parent not in sys.path:
            sys.path.insert(0, str(parent))
            break
else:
    raise ImportError("Could not find 'src' directory in the path hierarchy")

from raft_stubs.stubs import DeckStub, RaftServerStub

async def run_aiozmq_server(host, port, delete_db):
    """Run aiozmq stub server"""
    import aiozmq.rpc
    from tx_aiozmq.rpc_server import RPCServer
    
    print(f"Starting aiozmq stub server on {host}:{port}")
    
    raft_server = RaftServerStub(DeckStub(delete_db))
    rpc_server = RPCServer(raft_server)
    azmq_server = await aiozmq.rpc.serve_rpc(
        rpc_server,
        bind=f'tcp://{host}:{port}'
    )
    
    print(f"aiozmq server running on {host}:{port} - Press Ctrl+C to stop")
    
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        print("\nShutting down aiozmq server...")
    finally:
        azmq_server.close()
        await azmq_server.wait_closed()
        print("aiozmq server stopped.")

async def run_grpc_server(host, port, delete_db):
    """Run gRPC stub server"""
    from tx_grpc.rpc_helper import RPCHelper
    
    print(f"Starting gRPC stub server on {host}:{port}")
    
    raft_server = RaftServerStub(DeckStub(delete_db))
    rpc_helper = RPCHelper(port)
    rpc_server = await rpc_helper.get_rpc_server(raft_server)
    
    print(f"gRPC server running on {host}:{port} - Press Ctrl+C to stop")
    
    try:
        await rpc_helper.start_server_task()
        while rpc_helper.server_task is not None:
            await asyncio.sleep(0.001)
    except KeyboardInterrupt:
        print("\nShutting down gRPC server...")
        await rpc_helper.stop_server_task()
    finally:
        print("gRPC server stopped.")

async def run_fastapi_server(host, port, delete_db):
    """Run FastAPI stub server"""
    from tx_fastapi.rpc_helper import RPCHelper
    
    print(f"Starting FastAPI stub server on {host}:{port}")
    
    raft_server = RaftServerStub(DeckStub(delete_db))
    rpc_helper = RPCHelper(port)
    rpc_server = await rpc_helper.get_rpc_server(raft_server)
    
    print(f"FastAPI server running on {host}:{port} - Press Ctrl+C to stop")
    
    try:
        await rpc_helper.start_server_task()
        while rpc_helper.server_task is not None:
            await asyncio.sleep(0.001)
    except KeyboardInterrupt:
        print("\nShutting down FastAPI server...")
        await rpc_helper.stop_server_task()
    finally:
        print("FastAPI server stopped.")

async def run_astream_server(host, port, delete_db):
    """Run AsyncStream stub server"""
    from tx_astream.rpc_helper import RPCHelper
    
    print(f"Starting AsyncStream stub server on {host}:{port}")
    
    raft_server = RaftServerStub(DeckStub(delete_db))
    rpc_helper = RPCHelper(port)
    rpc_server = await rpc_helper.get_rpc_server(raft_server)
    
    print(f"AsyncStream server running on {host}:{port} - Press Ctrl+C to stop")
    
    try:
        await rpc_helper.start_server_task()
        while rpc_helper.server_task is not None:
            await asyncio.sleep(0.001)
    except KeyboardInterrupt:
        print("\nShutting down AsyncStream server...")
        await rpc_helper.stop_server_task()
    finally:
        print("AsyncStream server stopped.")

async def main():
    parser = argparse.ArgumentParser(
        description='Unified Raft Banking Stub Server',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --transport grpc --port 50350
  %(prog)s --transport aiozmq --host 0.0.0.0 --port 50150
  %(prog)s --transport fastapi --base-port 8000  # Uses port 8200

Available transports:
  astream, aiozmq, fastapi, grpc
        """)
    
    parser.add_argument('--transport', '-t', 
                        choices=['astream', 'aiozmq', 'fastapi', 'grpc'],
                        required=True,
                        help='Transport mechanism to use')
    parser.add_argument('--host', type=str, default='localhost',
                        help='Host to bind to (default: localhost)')
    parser.add_argument('--port', '-p', type=int, default=None,
                        help='Port to bind to (overrides base-port calculation)')
    parser.add_argument('--base-port', '-b', type=int, default=50050,
                        help='Base port for transport offset calculation (default: 50050)')
    parser.add_argument('--delete_db',  action='store_true',
                        help='Delete target db before running')
    
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
    
    # Run the appropriate server
    if args.transport == 'aiozmq':
        await run_aiozmq_server(args.host, port, args.delete_db)
    elif args.transport == 'grpc':
        await run_grpc_server(args.host, port, args.delete_db)
    elif args.transport == 'fastapi':
        await run_fastapi_server(args.host, port, args.delete_db)
    elif args.transport == 'astream':
        await run_astream_server(args.host, port, args.delete_db)
    else:
        raise ValueError(f"Unsupported transport: {args.transport}")

if __name__ == "__main__":
    asyncio.run(main())
