import asyncio
import logging
import traceback
import json
from fastapi import FastAPI, Request
import uvicorn
from raftengine.api.deck_api import CommandResult
from raftengine.deck.log_control import LogController
log_controller = LogController.get_controller()
logger = log_controller.add_logger('transport.server.fastapi')


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
            try:
                logger.debug(f"Processing command via FastAPI from {request.client}")
                data = await request.json()
                result = await self.raft_server.run_command(data["command"])
                return json.dumps(result, default=lambda o:o.__dict__)
            except Exception as e:
                logger.error(f"Error processing command: {traceback.format_exc()}")
                logger.debug(traceback.format_exc())
                raise
        
        @self.app.post("/raft_message")
        async def raft_message(request: Request):
            """Handle raft message requests"""
            try:
                logger.debug(f"Processing raft message via FastAPI from {request.client}")
                data = await request.json()
                # result is always None and we don't want to wait
                asyncio.create_task(self.raft_server.raft_message(data["message"]))
                return {"result": None}
            except Exception as e:
                logger.error(f"Error processing raft message: {e}")
                logger.debug(traceback.format_exc())
                raise

        @self.app.post("/local_command")
        async def local_command(request: Request):
            """Handle banking command requests"""
            try:
                logger.debug(f"Processing local command via FastAPI from {request.client}")
                data = await request.json()
                result = await self.raft_server.local_command(data["command"])
                return json.dumps(result, default=lambda o:o.__dict__)
            except Exception as e:
                logger.error(f"Error processing local command: {e}")
                logger.debug(traceback.format_exc())
                raise
        

async def start_server(raft_server, host='localhost', port=8000):
    """Start the FastAPI server"""
    logger.info(f"Starting FastAPI server on {host}:{port}")
    banking_server = RPCServer(raft_server)
    config = uvicorn.Config(banking_server.app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()
    logger.info(f"FastAPI server stopped")
