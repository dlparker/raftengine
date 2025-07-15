#!/usr/bin/env python
import asyncio
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
    host = "localhost"
    port = 50150
    raft_server = RaftServerStub(DeckStub())
    rpc_server = RPCServer(raft_server)
    azmq_server = await aiozmq.rpc.serve_rpc(
        rpc_server,
        bind=f'tcp://{host}:{port}'
    )
    try:
        # Keep the server running
        await asyncio.Event().wait()
    finally:
        azmq_server.close()
        await azmq_server.wait_closed()

if __name__=="__main__":
    asyncio.run(main())
