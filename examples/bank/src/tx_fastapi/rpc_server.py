import asyncio
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

class CommandRequest(BaseModel):
    command: str

class CommandResponse(BaseModel):
    result: str

class RaftRequest(BaseModel):
    message: str

class RaftResponse(BaseModel):
    result: str

class BankingServer:
    """FastAPI server implementing the banking service interface"""
    
    def __init__(self, raft_server):
        self.raft_server = raft_server
        self.app = FastAPI(title="Banking Service")
        self._setup_routes()
    
    def _setup_routes(self):
        """Setup FastAPI routes"""
        
        @self.app.post("/send_command", response_model=CommandResponse)
        async def send_command(request: CommandRequest):
            """Handle banking command requests"""
            try:
                result = await self.raft_server.run_command(request.command)
                return CommandResponse(result=result)
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/raft_message", response_model=RaftResponse)
        async def raft_message(request: RaftRequest):
            """Handle raft message requests"""
            try:
                result = await self.raft_server.raft_message(request.message)
                return RaftResponse(result=result)
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

async def start_server(raft_server, host='localhost', port=8000):
    """Start the FastAPI server"""
    banking_server = BankingServer(raft_server)
    config = uvicorn.Config(banking_server.app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()