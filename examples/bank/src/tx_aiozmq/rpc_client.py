import asyncio
import logging
import traceback
import aiozmq.rpc
from base.rpc_api import RPCAPI
from raftengine.api.deck_api import CommandResult

logger = logging.getLogger('bank.transport.client.aiozmq')

class RPCClient(RPCAPI):

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.client = None
        self.uri = f'tcp://{self.host}:{self.port}'

    def get_uri(self):
        return self.uri

    async def connect(self):
        logger.debug(f"Establishing ZeroMQ connection to {self.uri}")
        self.client = await aiozmq.rpc.connect_rpc(
            connect=self.uri
        )
        logger.info(f"Connected to ZeroMQ server at {self.uri}")

    async def run_command(self, command):
        if self.client is None:
            await self.connect()
        try:
            result = await self.client.call.run_command(command)
            return CommandResult(**result)
        except Exception as e:
            logger.error(f"Error running command: {e}")
            logger.debug(traceback.format_exc())
            raise

    async def raft_message(self, message):
        if self.client is None:
            await self.connect()
        # We don't need the reply which is always none and waiting for it slows
        # down the Raft operations, so just spawn a task to do the message
        # delivery and return right away. The messages and the code
        # that uses them are designed to work with fully async message passing
        # mechanisms that do not reply to the message like an RPC does.
        async def message_sender(msg):
            try:
                result = await self.client.call.raft_message(msg)
            except Exception as e:
                # Raft messages are fire-and-forget, so don't propagate errors
                logger.debug(f"Raft message send failed (expected): {e}")
        asyncio.create_task(message_sender(message))
        return None
    
    async def local_command(self, command:str) -> str:
        if self.client is None:
            await self.connect()
        try:
            return await self.client.call.local_command(command)
        except Exception as e:
            logger.error(f"Error running local command: {e}")
            logger.debug(traceback.format_exc())
            raise
    
    async def close(self):
        """Close the client connection"""
        if self.client is not None:
            logger.debug(f"Closing ZeroMQ connection to {self.uri}")
            self.client.close()
            await self.client.wait_closed()
            self.client = None
            logger.debug(f"ZeroMQ connection to {self.uri} closed")
    
