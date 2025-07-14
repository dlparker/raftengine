import asyncio
import aiozmq.rpc

class RPCClient:

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.client = None

    async def connect(self):
        uri = f'tcp://{self.host}:{self.port}'
        self.client = await aiozmq.rpc.connect_rpc(
            connect=uri
        )

    async def send_command(self, command):
        if self.client is None:
            await self.connect()
        return await self.client.call.send_command(command)

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
    
