#!/usr/bin/env python
import asyncio
from pathlib import Path
import sys
import grpc

this_dir = Path(__file__).resolve().parent
for parent in this_dir.parents:
    if parent.name == 'src':
        if parent not in sys.path:
            sys.path.insert(0, str(parent))
            break
else:
    raise ImportError("Could not find 'src' directory in the path hierarchy")

from tx_grpc.rpc_server import BankingServicer
from tx_grpc import banking_pb2_grpc
from raft_stubs.stubs import DeckStub
from raft_stubs.stubs import RaftServerStub

async def main():
    host = "localhost"
    port = 50052
    raft_server = RaftServerStub(DeckStub())
    
    # Create gRPC server
    server = grpc.aio.server()
    servicer = BankingServicer(raft_server)
    banking_pb2_grpc.add_BankingServiceServicer_to_server(servicer, server)
    
    listen_addr = f'{host}:{port}'
    server.add_insecure_port(listen_addr)
    
    await server.start()
    print(f"gRPC server started on {listen_addr}")
    
    try:
        # Keep the server running
        await server.wait_for_termination()
    finally:
        await server.stop(grace=5)

if __name__=="__main__":
    asyncio.run(main())