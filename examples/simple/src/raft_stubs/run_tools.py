
from split_base.collector import Collector
from raft_stubs.raft_server import RaftServerStub
from raft_stubs.raft_client import RaftClient

class RunTools:

    @staticmethod
    async def make_server(reload=False, port=50045):
        server = RaftServerStub(port, clear=not reload)
        await server.start()
        return server

    @staticmethod
    async def make_client(port=50045):
        client = RaftClient(f"aiozmq://localhost:{port}")
        return Collector(client),client
