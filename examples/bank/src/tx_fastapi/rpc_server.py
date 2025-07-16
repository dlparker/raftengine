import asyncio
import json
from fastapi import FastAPI, Request
import uvicorn
from raftengine.api.deck_api import CommandResult

class RPCServer:
    """FastAPI server implementing the banking service interface"""
    
    def __init__(self, raft_server):
        self.raft_server = raft_server
        self.app = FastAPI(title="Banking Service")
        self._setup_routes()
    
    def _setup_routes(self):
        """Setup FastAPI routes"""
        
        @self.app.post("/run_command")
        async def run_command(request: Request):
            """Handle banking command requests"""
            data = await request.json()
            result = await self.raft_server.run_command(data["command"])
            return json.dumps(result, default=lambda o:o.__dict__)
        
        @self.app.post("/raft_message")
        async def raft_message(request: Request):
            """Handle raft message requests"""
            data = await request.json()
            # result is always None and we don't want to wait
            asyncio.create_task(self.raft_server.raft_message(data["message"]))
            return {"result": None}

async def start_server(raft_server, host='localhost', port=8000):
    """Start the FastAPI server"""
    banking_server = RPCServer(raft_server)
    config = uvicorn.Config(banking_server.app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()
