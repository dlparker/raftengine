import asyncio
import logging
import traceback
import aiozmq.rpc
from raftengine.api.deck_api import CommandResult

logger = logging.getLogger('bank.transport.server.aiozmq')

class RPCServer(aiozmq.rpc.AttrHandler):

    def __init__(self, raft_server):
        self.raft_server = raft_server

    @aiozmq.rpc.method
    async def run_command(self, command):
        try:
            logger.debug(f"Processing command via ZeroMQ")
            result = await self.raft_server.run_command(command)
            return result.__dict__
        except Exception as e:
            logger.error(f"Error processing command: {e}")
            logger.debug(traceback.format_exc())
            raise

    @aiozmq.rpc.method
    async def raft_message(self, message):
        try:
            logger.debug(f"Processing raft message via ZeroMQ")
            return await self.raft_server.raft_message(message)
        except Exception as e:
            logger.error(f"Error processing raft message: {e}")
            logger.debug(traceback.format_exc())
            raise

    @aiozmq.rpc.method
    async def local_command(self, command):
        try:
            logger.debug(f"Processing local command via ZeroMQ")
            return await self.raft_server.local_command(command)
        except Exception as e:
            logger.error(f"Error processing local command: {e}")
            logger.debug(traceback.format_exc())
            raise
