import asyncio
from base.rpc_helper import RPCHelperAPI
from tx_astream.rpc_client import RPCClient
from tx_astream.rpc_server import RPCServer





class RPCHelper(RPCHelperAPI):

    def __init__(self, port=None): # port not used for client maker
        self.port = port
        self.sock_server = None
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
        self.sock_server = await asyncio.start_server(
            self.rpc_server.handle_client, '127.0.0.1', self.port
        )
        print(f"AsyncStream rpc server created on {self.port}")
        async def serve():
            try:
                # Keep the server running
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                # Server is being shut down
                pass
            finally:
                if self.sock_server:
                    self.sock_server.close()
                    try:
                        await self.sock_server.wait_closed()
                    except asyncio.CancelledError:
                        pass
                self.server_task = None
        self.server_task = asyncio.create_task(serve())
                
    async def stop_server_task(self):
        if self.sock_server:
            self.sock_server.close()
            try:
                await self.sock_server.wait_closed()
            except asyncio.CancelledError:
                pass
            self.sock_server = None
        if self.server_task:
            self.server_task.cancel()
            try:
                await self.server_task
            except asyncio.CancelledError:
                pass
            self.server_task = None
        
    
