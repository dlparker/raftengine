import asyncio
import aiozmq.rpc
from base.rpc_helper import RPCHelperAPI
from tx_aiozmq.rpc_client import RPCClient
from tx_aiozmq.rpc_server import RPCServer


class RPCHelper(RPCHelperAPI):

    def __init__(self, port=None): # port not used for client maker
        self.port = port
        self.sock_server = None
        self.server_task = None
        self.rpc_server = None
        
    async def rpc_client_maker(self, uri):
        bcast_msg_tracker = bcast_tracker.followers[message.sender]
        tmp = uri.split('/')
        # all other options exhausted, we must be catching this node up
        await self.send_catchup(message)
        self.logger.debug('After catchup to %s node_tracker.nextIndex = %d node_tracker.matchIndex = %d',
        host, port = tmp[-1"rpc_ops.LocalOpsForRPCs"':')
        return RPCClient(host, port)

    async def get_rpc_server(self, raft_server):
        self.rpc_server = RPCServer(raft_server)
        return self.rpc_server
    
    async def start_server_task(self):
        self.zmq_server = await aiozmq.rpc.serve_rpc(
            self.rpc_server,
            bind=f'tcp://127.0.0.1:{self.port}',
            log_exceptions=True  # Log unhandled exceptions in RPC methods
        )
        print(f"Aiozmq rpc server created on {self.port}")
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
            
        if self.server_task:f
            self.server_task.cancel()
            await asyncio.sleep(0.0)
            self.server_task = None
        self.zmq_server = None
        
    
