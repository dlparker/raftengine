import asyncio
from pathlib import Path
from base.counters import Counters
from base.validator import Validator
from split_base.collector import Collector
from split_base.dispatcher import Dispatcher
from rpc.raft_stub import RaftServerStub
#from rpc.rpc_client import RPCClient
#from rpc.rpc_server import RPCServer

from raftengine.extras.astream_rpc import RPCClient
from raftengine.extras.astream_rpc import RPCServer

class RunTools:

    @staticmethod
    async def make_server(port=50040):
        storage_dir = "/tmp"
        db_file = Path(storage_dir, 'counters.pickle')
        if db_file.exists():
            db_file.unlink()
        counters = Counters(storage_dir)
        dispatcher = Dispatcher(counters)
        server = RaftServerStub(RPCServer, dispatcher, port)
        return server

    @staticmethod
    async def make_client(host="localhost", port=50040):
        rpc_client = RPCClient(host, port)
        collector = Collector(rpc_client)
        return collector, rpc_client
