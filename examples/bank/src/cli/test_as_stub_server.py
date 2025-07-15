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
from tx_astream.rpc_helper import RPCHelper
from raft_stubs.stubs import DeckStub
from raft_stubs.stubs import RaftServerStub

async def main():
    port = 50060
    raft_server = RaftServerStub(DeckStub())
    rpc_helper = RPCHelper(port)
    rpc_server = await rpc_helper.get_rpc_server(raft_server)
    print(f'running on port {port}')
    await rpc_helper.start_server_task()
    while rpc_helper.server_task is not None:
        await asyncio.sleep(0.001)    

if __name__=="__main__":
    asyncio.run(main())
