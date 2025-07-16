import asyncio
import aiohttp
import json
from base.rpc_api import RPCAPI
from raftengine.api.deck_api import CommandResult

class RPCClient(RPCAPI):
    
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self.session = None
    
    def get_uri(self):
        return f"fasapi://{self.host}:{self.port}"

    async def connect(self):
        """Create HTTP session"""
        self.session = aiohttp.ClientSession()
    
    async def run_command(self, command):
        """Send a banking command to the server"""
        if self.session is None:
            await self.connect()
        
        url = f"{self.base_url}/run_command"
        data = {"command": command}
        
        async with self.session.post(url, json=data) as response:
            if response.status == 200:
                result = await response.json()
                cmd_result = CommandResult(**json.loads(result))
                return cmd_result
            else:
                error_text = await response.text()
                raise Exception(f"HTTP {response.status}: {error_text}")
    
    async def raft_message(self, message):
        """Send a raft message to the server"""
        if self.session is None:
            await self.connect()
        
        url = f"{self.base_url}/raft_message"
        data = {"message": message}

        async def responder():
            async with self.session.post(url, json=data) as response:
                if response.status == 200:
                    result = await response.json()
                    return result["result"]
                else:
                    error_text = await response.text()
                    raise Exception(f"HTTP {response.status}: {error_text}")
        # We don't need the reply which is always none and waiting for it slows
        # down the Raft operations, so just spawn a task to do the message
        # delivery and return right away. The messages and the code
        # that uses them are designed to work with fully async message passing
        # mechanisms that do not reply to the message like an RPC does.
        asyncio.create_task(responder())
        return
    
    async def close(self):
        """Close the HTTP session"""
        if self.session is not None:
            await self.session.close()
            self.session = None
            
    async def __aenter__(self):
        """Async context manager entry"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()
