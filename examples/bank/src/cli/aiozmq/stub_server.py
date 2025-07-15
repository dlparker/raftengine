#!/usr/bin/env python
import asyncio
import argparse
from pathlib import Path
import sys
import aiozmq.rpc

this_dir = Path(__file__).resolve().parent
for parent in this_dir.parents:
    if parent.name == 'src':
        if parent not in sys.path:
            sys.path.insert(0, str(parent))
            break
else:
    raise ImportError("Could not find 'src' directory in the path hierarchy")
from tx_aiozmq.rpc_server import RPCServer
from raft_stubs.stubs import DeckStub
from raft_stubs.stubs import RaftServerStub

async def main():
    parser = argparse.ArgumentParser(
        description='Raft Banking ZeroMQ stub server')
    
    parser.add_argument('--host', type=str, default='localhost',
                        help='host to bind to, default=localhost')
    parser.add_argument('--port', '-p', type=int, default=50150,
                        help='port to bind to, default=50150')
    
    args = parser.parse_args()
    
    host = args.host
    port = args.port
    
    print(f"Starting ZeroMQ stub server on {host}:{port}")
    
    raft_server = RaftServerStub(DeckStub())
    rpc_server = RPCServer(raft_server)
    azmq_server = await aiozmq.rpc.serve_rpc(
        rpc_server,
        bind=f'tcp://{host}:{port}'
    )
    
    print(f"Server running on {host}:{port} - Press Ctrl+C to stop")
    
    try:
        # Keep the server running
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        print("\nShutting down server...")
    finally:
        azmq_server.close()
        await azmq_server.wait_closed()
        print("Server stopped.")

if __name__=="__main__":
    asyncio.run(main())
