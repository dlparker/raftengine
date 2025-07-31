import asyncio
import logging
import traceback
import json
from fastapi import FastAPI, Request
import uvicorn
logger = logging.getLogger('transport.server.fastapi')


class RPCServer:
    """FastAPI server implementing the banking service interface"""
    
    def __init__(self, raft_server):
        self.raft_server = raft_server
        self.app = FastAPI(title="Raft Enabled RPC Service")
        self._setup_routes()
        self.uvicorn_server = None
        self.port = None

    async def start(self, port):
        if self.uvicorn_server:
            return
        self.port = port
        config = uvicorn.Config(
            self.app, 
            host='localhost',
            port=self.port, 
            log_level="error",
            # Optimize for high concurrency multi-client scenarios
            backlog=2048,  # Increase connection backlog
            limit_concurrency=1000,  # Allow more concurrent requests
            limit_max_requests=10000,  # Increase max requests per worker
            timeout_keep_alive=30,  # Keep connections alive longer
        )
        self.uvicorn_server = uvicorn.Server(config)
        async def serve():
            try:
                # Keep the server running
                await self.uvicorn_server.serve()
            except asyncio.exceptions.CancelledError:
                pass
            finally:
                self.server_task = None
        self.server_task = asyncio.create_task(serve())
                
    async def stop(self):
        if self.uvicorn_server:
            self.uvicorn_server.should_exit = True
            # Give server more time to gracefully shut down
            for _ in range(10):  # Wait up to 1 second
                if not self.uvicorn_server.started:
                    break
                await asyncio.sleep(0.1)
        if self.server_task:
            if not self.server_task.done():
                self.server_task.cancel()
                try:
                    await self.server_task
                except asyncio.CancelledError:
                    pass
            self.server_task = None
        
    def _setup_routes(self):
        
        @self.app.post("/issue_command")
        async def issue_command(request: Request):
            try:
                logger.debug(f"Processing command via FastAPI from {request.client}")
                data = await request.json()
                result = await self.raft_server.issue_command(data["command"])
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

        @self.app.post("/direct_server_command")
        async def direct_server_command(request: Request):
            try:
                logger.debug(f"Processing local command via FastAPI from {request.client}")
                data = await request.json()
                result = await self.raft_server.direct_server_command(data["command"])
                return json.dumps(result, default=lambda o:o.__dict__)
            except asyncio.exceptions.CancelledError:
                pass
            except Exception as e:
                logger.error(f"Error processing local command: {e}")
                logger.debug(traceback.format_exc())
                raise
