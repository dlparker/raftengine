
from split_base.collector import Collector
from raft_stubs.raft_server import RaftServerStub
from raft_stubs.raft_client import RaftClient

class RunTools:

    @staticmethod
    async def make_server(reload=False):
        server = RaftServerStub(50045, clear=not reload)
        await server.start()

    @staticmethod
    async def make_client():
        client = RaftClient(f"aiozmq://localhost:50045")
        return Collector(client)
