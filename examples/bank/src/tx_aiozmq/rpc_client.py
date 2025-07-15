import asyncio
import aiozmq.rpc
from base.rpc_api import RPCAPI
from raftengine.api.deck_api import CommandResult

class RPCClient(RPCAPI):

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.client = None

    async def connect(self):
        uri = f'tcp://{self.host}:{self.port}'
        self.client = await aiozmq.rpc.connect_rpc(
            connect=uri
        )

    async def run_command(self, command):
        if self.client is None:
            await self.connect()
        result = await self.client.call.run_command(command)
        return CommandResult(**result)

    async def raft_message(self, message):
        if self.client is None:
            await self.connect()
        return await self.client.call.raft_message(message)
    
    async def close(self):
        """Close the client connection"""
        if self.client is not None:
            self.client.close()
            await self.client.wait_closed()
            self.client = None
    
