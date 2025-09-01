import asyncio
import aiozmq.rpc

class RPCServer(aiozmq.rpc.AttrHandler):

    def __init__(self, raft_server, timeout=10.0):
        self.raft_server = raft_server
        self.zmq_server = None
        self.server_port = None
        self.timeout = timeout
        
    async def start(self, port):
        self.server_port = port
        self.zmq_server = await aiozmq.rpc.serve_rpc(
            self,
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

    async def stop(self):
        if self.zmq_server:
            self.zmq_server.close()
            await self.zmq_server.wait_closed()
        if self.server_task:
            self.server_task.cancel()
            await asyncio.sleep(0.0)
            self.server_task = None
        self.zmq_server = None
        

    @aiozmq.rpc.method
    async def issue_command(self, command, timeout):
        result = await self.raft_server.issue_command(command, timeout)
        return result

    @aiozmq.rpc.method
    async def raft_message(self, message):
        result = await self.raft_server.raft_message(message)
        return result

    @aiozmq.rpc.method
    async def direct_server_command(self, command):
        result = await self.raft_server.direct_server_command(command)
        return result




