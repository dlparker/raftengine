import asyncio
import aiohttp
import json

class RPCClient:
    """FastAPI HTTP client for banking service"""
    
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self.session = None
    
    async def connect(self):
        """Create HTTP session"""
        self.session = aiohttp.ClientSession()
    
    async def send_command(self, command):
        """Send a banking command to the server"""
        if self.session is None:
            await self.connect()
        
        url = f"{self.base_url}/send_command"
        data = {"command": command}
        
        async with self.session.post(url, json=data) as response:
            if response.status == 200:
                result = await response.json()
                return result["result"]
            else:
                error_text = await response.text()
                raise Exception(f"HTTP {response.status}: {error_text}")
    
    async def raft_message(self, message):
        """Send a raft message to the server"""
        if self.session is None:
            await self.connect()
        
        url = f"{self.base_url}/raft_message"
        data = {"message": message}
        
        async with self.session.post(url, json=data) as response:
            if response.status == 200:
                result = await response.json()
                return result["result"]
            else:
                error_text = await response.text()
                raise Exception(f"HTTP {response.status}: {error_text}")
    
    async def close(self):
        """Close the HTTP session"""
        if self.session is not None:
            await self.session.close()
            self.session = None