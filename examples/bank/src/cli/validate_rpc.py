#!/usr/bin/env python
"""
Unified RPC validation tool that combines stub_server and test_client functionality.
Runs the server in the background, executes the client validation, then shuts down the server.
"""
import asyncio
import argparse
import signal
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
from raft_stubs.stubs import DeckStub, RaftServerStub

class ServerManager:
    """Manages background server lifecycle"""
    
    def __init__(self, transport, host, port, delete_db):
        self.transport = transport
        self.host = host
        self.port = port
        self.delete_db = delete_db
        self.server_task = None
        self.server_instance = None
        
    async def start_server(self):
        """Start the appropriate server in the background"""
        if self.transport == 'aiozmq':
            await self._start_aiozmq_server()
        elif self.transport == 'grpc':
            await self._start_grpc_server()
        elif self.transport == 'fastapi':
            await self._start_fastapi_server()
        elif self.transport == 'astream':
            await self._start_astream_server()
        else:
            raise ValueError(f"Unsupported transport: {self.transport}")
            
    async def _start_aiozmq_server(self):
        """Start aiozmq server"""
        import aiozmq.rpc
        from tx_aiozmq.rpc_server import RPCServer
        
        print(f"Starting aiozmq server on {self.host}:{self.port}")
        
        raft_server = RaftServerStub(DeckStub(self.delete_db))
        rpc_server = RPCServer(raft_server)
        self.server_instance = await aiozmq.rpc.serve_rpc(
            rpc_server,
            bind=f'tcp://{self.host}:{self.port}'
        )
        
        # Create a task to keep the server running
        self.server_task = asyncio.create_task(self._keep_server_running())
        
    async def _start_grpc_server(self):
        """Start gRPC server"""
        from tx_grpc.rpc_helper import RPCHelper
        
        print(f"Starting gRPC server on {self.host}:{self.port}")
        
        raft_server = RaftServerStub(DeckStub(self.delete_db))
        rpc_helper = RPCHelper(self.port)
        rpc_server = await rpc_helper.get_rpc_server(raft_server)
        
        self.server_instance = rpc_helper
        await rpc_helper.start_server_task()
        
        # Create a task to keep the server running
        self.server_task = asyncio.create_task(self._keep_grpc_server_running(rpc_helper))
        
    async def _start_fastapi_server(self):
        """Start FastAPI server"""
        from tx_fastapi.rpc_helper import RPCHelper
        
        print(f"Starting FastAPI server on {self.host}:{self.port}")
        
        raft_server = RaftServerStub(DeckStub(self.delete_db))
        rpc_helper = RPCHelper(self.port)
        rpc_server = await rpc_helper.get_rpc_server(raft_server)
        
        self.server_instance = rpc_helper
        await rpc_helper.start_server_task()
        
        # Create a task to keep the server running
        self.server_task = asyncio.create_task(self._keep_fastapi_server_running(rpc_helper))
        
    async def _start_astream_server(self):
        """Start AsyncStream server"""
        from tx_astream.rpc_helper import RPCHelper
        
        print(f"Starting AsyncStream server on {self.host}:{self.port}")
        
        raft_server = RaftServerStub(DeckStub(self.delete_db))
        rpc_helper = RPCHelper(self.port)
        rpc_server = await rpc_helper.get_rpc_server(raft_server)
        
        self.server_instance = rpc_helper
        await rpc_helper.start_server_task()
        
        # Create a task to keep the server running
        self.server_task = asyncio.create_task(self._keep_astream_server_running(rpc_helper))
        
    async def _keep_server_running(self):
        """Keep aiozmq server running"""
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            pass
            
    async def _keep_grpc_server_running(self, rpc_helper):
        """Keep gRPC server running"""
        try:
            while rpc_helper.server_task is not None:
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            pass
            
    async def _keep_fastapi_server_running(self, rpc_helper):
        """Keep FastAPI server running"""
        try:
            while rpc_helper.server_task is not None:
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            pass
            
    async def _keep_astream_server_running(self, rpc_helper):
        """Keep AsyncStream server running"""
        try:
            while rpc_helper.server_task is not None:
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            pass
            
    async def stop_server(self):
        """Stop the server"""
        if self.server_task:
            self.server_task.cancel()
            try:
                await self.server_task
            except asyncio.CancelledError:
                pass
                
        if self.server_instance:
            if self.transport == 'aiozmq':
                self.server_instance.close()
                await self.server_instance.wait_closed()
            elif self.transport in ['grpc', 'fastapi', 'astream']:
                await self.server_instance.stop_server_task()
                
        # Extra time for cleanup
        await asyncio.sleep(0.2)
        print(f"Stopped {self.transport} server")

async def create_client(transport, host, port):
    """Create the appropriate RPC client"""
    if transport == 'aiozmq':
        from tx_aiozmq.rpc_helper import RPCHelper
        uri = f"grpc://{host}:{port}"
        return await RPCHelper().rpc_client_maker(uri)
    elif transport == 'grpc':
        from tx_grpc.rpc_helper import RPCHelper
        uri = f"grpc://{host}:{port}"
        return await RPCHelper().rpc_client_maker(uri)
    elif transport == 'fastapi':
        from tx_fastapi.rpc_helper import RPCHelper
        uri = f"fastapi://{host}:{port}"
        return await RPCHelper().rpc_client_maker(uri)
    elif transport == 'astream':
        from tx_astream.rpc_helper import RPCHelper
        uri = f"astream://{host}:{port}"
        return await RPCHelper().rpc_client_maker(uri)
    else:
        raise ValueError(f"Unsupported transport: {transport}")

async def main():
    parser = argparse.ArgumentParser(
        description='Unified RPC Validation Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --transport grpc demo --random
  %(prog)s --transport aiozmq test --loops 10 --json-output results.json
  %(prog)s --transport fastapi test --loops 5 --no-timing
  %(prog)s --transport grpc --port 8300 test --check-raft

Available transports:
  astream, aiozmq, fastapi, grpc
        """)
    
    parser.add_argument('--transport', '-t', 
                        choices=['astream', 'aiozmq', 'fastapi', 'grpc'],
                        required=True,
                        help='Transport mechanism to use')
    parser.add_argument('--host', type=str, default='localhost',
                        help='Host to bind/connect to (default: localhost)')
    parser.add_argument('--port', '-p', type=int, default=None,
                        help='Port to bind/connect to (overrides base-port calculation)')
    parser.add_argument('--base-port', '-b', type=int, default=50050,
                        help='Base port for transport offset calculation (default: 50050)')
    parser.add_argument('--server-startup-delay', type=float, default=1.0,
                        help='Delay in seconds to wait for server startup (default: 1.0)')
    parser.add_argument('--delete_db',  action='store_true',
                        help='Delete target db before running')
    
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
    
    # Create server manager
    server_manager = ServerManager(args.transport, args.host, port, args.delete_db)
    
    try:
        # Start server in background
        await server_manager.start_server()
        
        # Wait for server to start up
        await asyncio.sleep(args.server_startup_delay)
        
        print(f"Connecting to {args.transport} server at {args.host}:{port}")
        
        # Create client and run validation
        rpc_client = await create_client(args.transport, args.host, port)
        
        try:
            await validate(rpc_client, 
                           mode=args.mode,
                           loops=args.loops,
                           use_random_data=args.random,
                           print_timing=not args.no_timing,
                           json_output=args.json_output,
                           raft_stubs=args.raft_stubs)
            
            print(f"Successfully completed {args.transport} validation")
        finally:
            # Properly close client connections
            if hasattr(rpc_client, 'close'):
                await rpc_client.close()
                # Give client time to finish closing
                await asyncio.sleep(0.2)
        
    except Exception as e:
        print(f"Error during validation: {e}")
        sys.exit(1)
    finally:
        # Always stop the server
        await server_manager.stop_server()

if __name__ == "__main__":
    asyncio.run(main())
