import os
import asyncio
import logging
import uvicorn
from base.setup_helper import SetupHelperAPI
from base.client import Client
from base.operations import Ops
from step4.fastapi.server import create_server
from step4.fastapi.proxy import ServerProxy

# Configure logging
logging.basicConfig(
    level=logging.WARN,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SetupHelper(SetupHelperAPI):

    def __init__(self):
        self.port = None
        self.server = None
        
    async def get_client(self, host='127.0.0.1', port='8000'):
        proxy = await self.get_proxy(host=host, port=port)
        return Client(server_proxy=proxy)

    async def get_proxy(self, host='127.0.0.1', port='8000'):
        return ServerProxy(host, port)

    async def get_server(self, db_file: os.PathLike, port='8000'):
        server = Ops(db_file)
        self.port = port
        self.server = server
        return server
    
    async def serve(self, server=None):
        uvicorn_server = await start_server(server or self.server, self.port)
        try:
            logger.info(f"FastAPI JSON-RPC server started on port {self.port}")
            await uvicorn_server.serve()
        except KeyboardInterrupt:
            logger.info("Server interrupted by user")
        finally:
            logger.info("FastAPI JSON-RPC server stopped")


async def start_server(banking_server: Ops, port: str):
    """Start the FastAPI server with uvicorn"""
    # Enable asyncio debugging
    asyncio.get_event_loop().set_debug(True)
    logger.debug("Asyncio debug mode enabled")

    try:
        # Create the FastAPI app
        app = await create_server('127.0.0.1', int(port), banking_server)
        
        # Create uvicorn server config
        config = uvicorn.Config(
            app=app,
            host='127.0.0.1',
            port=int(port),
            log_level='info',
            access_log=True
        )
        
        # Create uvicorn server instance
        server = uvicorn.Server(config)
        logger.info(f"FastAPI JSON-RPC server created on 127.0.0.1:{port}")
        
        return server
        
    except Exception as e:
        logger.error(f"Failed to start FastAPI server: {e}", exc_info=True)
        raise
