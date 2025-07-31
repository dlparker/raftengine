import asyncio
from pathlib import Path
from base.counters import Counters
from base.validator import Validator
from split_base.collector import Collector
from split_base.dispatcher import Dispatcher
from rpc.raft_stub import RaftServerStub

class RunTools:

    def __init__(self, transport):
        if transport not in ['aiozmq','astream','fastapi','grpc']:
            raise Exception(f'Unknown transport {transport}')
        self.transport = transport
        if transport == 'aiozmq':
            from rpc.aiozmq.rpc_client import RPCClient
            from rpc.aiozmq.rpc_server import RPCServer
            self.client_class = RPCClient
            self.server_class = RPCServer
        elif transport == 'astream':
            from rpc.astream.rpc_client import RPCClient
            from rpc.astream.rpc_server import RPCServer
            self.client_class = RPCClient
            self.server_class = RPCServer
        elif transport == 'fastapi':
            from rpc.fastapi.rpc_client import RPCClient
            from rpc.fastapi.rpc_server import RPCServer
            self.client_class = RPCClient
            self.server_class = RPCServer
        elif transport == 'grpc':
            from rpc.grpc.rpc_client import RPCClient
            from rpc.grpc.rpc_server import RPCServer
            self.client_class = RPCClient
            self.server_class = RPCServer

    def get_client_class(self):
        return self.client_class

    def get_server_class(self):
        return self.server_class
    
    async def make_server(self, port=50040):
        storage_dir = "/tmp"
        db_file = Path(storage_dir, 'counters.pickle')
        if db_file.exists():
            db_file.unlink()
        counters = Counters(storage_dir)
        dispatcher = Dispatcher(counters)
        server = RaftServerStub(self.server_class, dispatcher, port)
        return server

    async def make_client(self, host="localhost", port=50040):
        rpc_client = self.client_class(host, port)
        collector = Collector(rpc_client)
        return collector, rpc_client
