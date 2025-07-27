import aiozmq.rpc

class RPCClient:

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.client = None
        self.aiozmq_uri = f'tcp://{self.host}:{self.port}'
        
    async def connect(self):
        self.client = await aiozmq.rpc.connect_rpc(
            connect=self.aiozmq_uri
        )
        
    async def run_command(self, command):
        if self.client is None:
            await self.connect()
        return await self.client.call.run_command(command)


    async def close(self):
        """Close the client connection"""
        if self.client is not None:
            self.client.close()
            await self.client.wait_closed()
            self.client = None
