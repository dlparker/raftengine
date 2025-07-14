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
from astream.rpc_server import RPCServer
from raft_stubs.stubs import DeckStub
from raft_stubs.stubs import RaftServerStub

async def main():
    port = 50050
    raft_server = RaftServerStub(DeckStub())
    rpc_server = RPCServer(raft_server, port)
    sock_server = await asyncio.start_server(
        rpc_server.handle_client, '127.0.0.1', port
    )
    print(f'running on port {port}')
    await sock_server.serve_forever()
    

if __name__=="__main__":
    asyncio.run(main())
