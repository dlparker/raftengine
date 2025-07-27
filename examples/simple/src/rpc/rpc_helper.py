import asyncio
import aiozmq.rpc
from rpc.rpc_client import RPCClient
from rpc.rpc_server import RPCServer

class RPCHelper:

    def __init__(self):
        self.sock_server = None
        self.server_task = None
        self.rpc_server = None
        self.server_port = None
        
    async def rpc_client_maker(self, host, port):
        return RPCClient(host, port)

    async def get_rpc_server(self, port, dispatcher):
        self.server_port = port
        self.rpc_server = RPCServer(dispatcher)
        return self.rpc_server
    
    async def start_server_task(self):
        self.zmq_server = await aiozmq.rpc.serve_rpc(
            self.rpc_server,
            bind=f'tcp://127.0.0.1:{self.server_port}',
            log_exceptions=True  # Log unhandled exceptions in RPC methods
        )
        print(f"Aiozmq rpc server created on {self.server_port}")
        async def serve():
            try:
                # Keep the server running
                await asyncio.Event().wait()
            finally:
                self.zmq_server.close()
                await self.zmq_server.wait_closed()
                self.server_task = None
        self.server_task = asyncio.create_task(serve())
                
    async def stop_server_task(self):
        if self.zmq_server:
            self.zmq_server.close()
            await self.zmq_server.wait_closed()
        if self.server_task:
            self.server_task.cancel()
            await asyncio.sleep(0.0)
            self.server_task = None
        self.zmq_server = None
