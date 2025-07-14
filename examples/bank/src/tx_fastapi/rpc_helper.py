import asyncio
import uvicorn
from base.rpc_helper import RPCHelperAPI
from tx_fastapi.rpc_client import RPCClient
from tx_fastapi.rpc_server import RPCServer


class RPCHelper(RPCHelperAPI):

    def __init__(self, port=None): # port not used for client maker
        self.port = port
        self.uvicorn_server = None
        self.server_task = None
        self.rpc_server = None
        
    async def rpc_client_maker(self, uri):
        tmp = uri.split('/')
        host, port = tmp[-1].split(':')
        return RPCClient(host, port)

    async def get_rpc_server(self, raft_server):
        self.rpc_server = RPCServer(raft_server)
        return self.rpc_server
    
    async def start_server_task(self):
        config = uvicorn.Config(self.rpc_server.app, host='localhost',
                                port=self.port, log_level="error")
        self.uvicorn_server = uvicorn.Server(config)
        
        print(f"FastAPI rpc server created on {self.port}")
        async def serve():
            try:
                # Keep the server running
                await self.uvicorn_server.serve()
            finally:
                self.server_task = None
        self.server_task = asyncio.create_task(serve())
                
    async def stop_server_task(self):
        if self.server_task:
            self.server_task.cancel()
            await asyncio.sleep(0.0)
            self.server_task = None
        
    
