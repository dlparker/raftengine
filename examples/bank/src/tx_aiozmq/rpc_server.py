import asyncio
import aiozmq.rpc
from raftengine.api.deck_api import CommandResult

class RPCServer(aiozmq.rpc.AttrHandler):

    def __init__(self, raft_server):
        self.raft_server = raft_server

    @aiozmq.rpc.method
    async def run_command(self, command):
        result = await self.raft_server.run_command(command)
        return result.__dict__

    @aiozmq.rpc.method
    async def raft_message(self, message):
        # we don't need the reply
        return await self.raft_server.raft_message(message)
