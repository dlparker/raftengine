import asyncio
import grpc
from base.rpc_helper import RPCHelperAPI
from tx_grpc.rpc_client import RPCClient
from tx_grpc.rpc_server import RPCServer
from tx_grpc import banking_pb2_grpc


class RPCHelper(RPCHelperAPI):

    def __init__(self, port=None): # port not used for client maker
        self.port = port
        self.server_task = None
        self.rpc_server = None
        self.aio_server = None
        
    async def rpc_client_maker(self, uri):
        tmp = uri.split('/')
        host, port = tmp[-1].split(':')
        return RPCClient(host, port)

    async def get_rpc_server(self, raft_server):
        self.rpc_server = RPCServer(raft_server)
        return self.rpc_server
    
    async def start_server_task(self):
        self.aio_server = grpc.aio.server()
        banking_pb2_grpc.add_BankingServiceServicer_to_server(self.rpc_server, self.aio_server)
    
        listen_addr = f'localhost:{self.port}'
        self.aio_server.add_insecure_port(listen_addr)
    
        await self.aio_server.start()
        print(f"gRPC rpc server created on {self.port}")
        async def serve():
            try:
                # Keep the server running
                await self.aio_server.wait_for_termination()
            finally:
                await self.aio_server.stop(grace=5)
        self.server_task = asyncio.create_task(serve())
                
    async def stop_server_task(self):
        if self.aio_server:
            await self.aio_server.stop(grace=1)
            self.aio_server = None
        if self.server_task:
            self.server_task.cancel()
            await asyncio.sleep(0.0)
            self.server_task = None
        
    
