import asyncio
from pathlib import Path
from base.counters import Counters
from base.validator import Validator
from split_base.collector import Collector
from split_base.dispatcher import Dispatcher
from rpc.raft_stub import RaftServerStub
from rpc.rpc_client import RPCClient

class RunTools:

    @staticmethod
    async def make_server(port=50040, reload=False):
        storage_dir = "/tmp"
        file_path = Path(storage_dir, 'counters.pickle')
        if file_path.exists() and not reload:
            file_path.unlink()
        counters = Counters(storage_dir)
        dispatcher = Dispatcher(counters)
        server = RaftServerStub(dispatcher, port)
        return server

    @staticmethod
    async def make_client(host="localhost", port=50040):
        rpc_client = RPCClient(host, port)
        collector = Collector(rpc_client)
        return collector, rpc_client
