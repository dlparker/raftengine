import asyncio
import logging
import traceback
import aiohttp
import json
logger = logging.getLogger('transport.client.fastapi')


class RPCClient:
    
    def __init__(self, host, port, timeout=1.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.base_url = f"http://{host}:{port}"
        self.session = None
    
    def get_uri(self):
        return f"fastapi://{self.host}:{self.port}"

    async def connect(self):
        logger.debug(f"Creating HTTP session for {self.base_url}")
        self.session = aiohttp.ClientSession()
        logger.info(f"Connected to FastAPI server at {self.base_url}")
    
    async def issue_command(self, command):
        if self.session is None:
            await self.connect()
        
        url = f"{self.base_url}/issue_command"
        data = {"command": command}
        
        try:
            async with self.session.post(url, json=data) as response:
                if response.status == 200:
                    result = await response.json()
                    if result is None:
                        raise Exception('got none back from server')
                    dres = json.loads(result)
                    return dres
                else:
                    error_text = await response.text()
                    logger.error(f"HTTP error {response.status}: {error_text}")
                    raise Exception(f"HTTP {response.status}: {error_text}")
        except Exception as e:
            logger.error(f"Error running command via FastAPI: {traceback.format_exc()}")
            logger.debug(traceback.format_exc())
            raise
    
    async def raft_message(self, message):
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
    
    async def direct_server_command(self, command):
        if self.session is None:
            await self.connect()
        
        url = f"{self.base_url}/direct_server_command"
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
            logger.error(f"Error running direct server command via FastAPI: {e}")
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
