import asyncio
import aiozmq.rpc
from base.rpc_api import RPCAPI
from raftengine.api.deck_api import CommandResult

class RPCClient(RPCAPI):

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.client = None
        self.uri = f'tcp://{self.host}:{self.port}'

    def get_uri(self):
        return self.uri

    async def connect(self):
        self.client = await aiozmq.rpc.connect_rpc(
            connect=self.uri
        )

    async def run_command(self, command):
        if self.client is None:
            await self.connect()
        result = await self.client.call.run_command(command)
        return CommandResult(**result)

    async def raft_message(self, message):
        if self.client is None:
            await self.connect()
        # We don't need the reply which is always none and waiting for it slows
        # down the Raft operations, so just spawn a task to do the message
        # delivery and return right away. The messages and the code
        # that uses them are designed to work with fully async message passing
        # mechanisms that do not reply to the message like an RPC does.
        asyncio.create_task(self.client.call.raft_message(message))
        return None
    
    async def close(self):
        """Close the client connection"""
        if self.client is not None:
            self.client.close()
            await self.client.wait_closed()
            self.client = None
    
