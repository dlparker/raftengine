#!/usr/bin/env python
import asyncio
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

from tx_fastapi.rpc_server import BankingServer
from raft_stubs.stubs import DeckStub
from raft_stubs.stubs import RaftServerStub
import uvicorn

async def main():
    host = "localhost"
    port = 8000
    raft_server = RaftServerStub(DeckStub())
    
    # Create FastAPI server
    banking_server = BankingServer(raft_server)
    config = uvicorn.Config(banking_server.app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    
    print(f"FastAPI server starting on {host}:{port}")
    await server.serve()

if __name__=="__main__":
    asyncio.run(main())