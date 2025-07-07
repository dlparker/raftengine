from src.no_raft.transports.async_streams.proxy import ServerProxy, ASServer, ASClient

from src.base.datatypes import CommandType
from src.base.client import Client
from src.base.server import Server

class RaftClient(Client):

    async def raft_message(self, in_message):
        return await self.server_proxy.raft_message(in_message)
    
class RaftServer(Server):

    async def raft_message(self, in_message):
        print(in_message)
        return in_message
    
class RaftASServer(ASServer):

    pass
    
class RaftServerProxy(ServerProxy):

    async def raft_message(self, in_message) -> None:
        args = locals()
        del args['self']
        return await self.as_client.do_command("raft_message", args)
    
def get_astream_client(host: str, port: int):
    """Create an async streams client"""
    as_client = ASClient(host, port) # Don't need our own version given how it works
    proxy = RaftServerProxy(as_client)
    client = RaftClient(proxy)

    async def cleanup():
        await as_client.close()

    return client, cleanup

