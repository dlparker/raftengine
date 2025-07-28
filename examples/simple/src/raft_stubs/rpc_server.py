import aiozmq.rpc
from rpc.rpc_server import RPCServer as BaseServer

class RPCServer(BaseServer):

    @aiozmq.rpc.method
    async def raft_message(self, message):
        result = await self.dispatcher.raft_message(message)
        return result
