import asyncio
import logging
import traceback
import aiohttp
import json
from base.rpc_api import RPCAPI
from raftengine.api.deck_api import CommandResult
from raftengine.deck.log_control import LogController
log_controller = LogController.get_controller()
logger = log_controller.add_logger('transport.client.fastapi')


class RPCClient(RPCAPI):
    
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self.session = None
    
    def get_uri(self):
        return f"fastapi://{self.host}:{self.port}"

    async def connect(self):
        """Create HTTP session"""
        logger.debug(f"Creating HTTP session for {self.base_url}")
        self.session = aiohttp.ClientSession()
        logger.info(f"Connected to FastAPI server at {self.base_url}")
    
    async def run_command(self, command):
        """Send a banking command to the server"""
        if self.session is None:
            await self.connect()
        
        url = f"{self.base_url}/run_command"
        data = {"command": command}
        
        try:
            async with self.session.post(url, json=data) as response:
                if response.status == 200:
                    result = await response.json()
                    cmd_result = CommandResult(**json.loads(result))
                    return cmd_result
                else:
                    error_text = await response.text()
                    logger.error(f"HTTP error {response.status}: {error_text}")
                    raise Exception(f"HTTP {response.status}: {error_text}")
        except Exception as e:
            logger.error(f"Error running command via FastAPI: {e}")
            logger.debug(traceback.format_exc())
            raise
    
    async def raft_message(self, message):
        """Send a raft message to the server"""
        if self.session is None:
            await self.connect()
        
        url = f"{self.base_url}/raft_message"
        data = {"message": message}

        async def responder():
            try:
                async with self.session.post(url, json=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result["result"]
                    else:
                        error_text = await response.text()
                        raise Exception(f"HTTP {response.status}: {error_text}")
            except Exception as e:
                # Raft messages are fire-and-forget, so don't propagate errors
                logger.debug(f"Raft message send failed (expected): {e}")
        # We don't need the reply which is always none and waiting for it slows
        # down the Raft operations, so just spawn a task to do the message
        # delivery and return right away. The messages and the code
        # that uses them are designed to work with fully async message passing
        # mechanisms that do not reply to the message like an RPC does.
        asyncio.create_task(responder())
        return
    
    async def local_command(self, command):
        """Send a side command to the server"""
        if self.session is None:
            await self.connect()
        
        url = f"{self.base_url}/local_command"
        data = {"command": command}
        
        try:
            async with self.session.post(url, json=data) as response:
                if response.status == 200:
                    result = await response.json()
                    return result
                else:
                    error_text = await response.text()
                    logger.error(f"HTTP error {response.status}: {error_text}")
                    raise Exception(f"HTTP {response.status}: {error_text}")
        except Exception as e:
            logger.error(f"Error running local command via FastAPI: {e}")
            logger.debug(traceback.format_exc())
            raise
            
    async def close(self):
        """Close the HTTP session"""
        if self.session is not None:
            logger.debug(f"Closing HTTP session to {self.base_url}")
            await self.session.close()
            self.session = None
            logger.debug(f"HTTP session to {self.base_url} closed")
            
    async def __aenter__(self):
        """Async context manager entry"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()
