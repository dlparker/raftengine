import asyncio
import aiozmq.rpc

class RPCServer(aiozmq.rpc.AttrHandler):

    def __init__(self, raft_server):
        self.raft_server = raft_server

    @aiozmq.rpc.method
    async def send_command(self, command):
        return await self.raft_server.send_command(command)

    @aiozmq.rpc.method
    async def raft_message(self, message):
        return await self.raft_server.raft_message(message)
