import aiozmq.rpc
from rpc.rpc_client import RPCClient as BaseClient

class RPCClient(BaseClient):

    async def raft_message(self, message):
        if self.client is None:
            await self.connect()
        return await self.client.call.raft_message(message)
