import os
import asyncio
import logging
from base.setup_helper import SetupHelperAPI
from step4.base_plus.client import Client
from base.operations import Ops
from step4.grpc.server import BankingServiceImpl, create_server
from step4.grpc.proxy import ServerProxy
from step4.raft_ops.collector import Collector
from step4.raft_ops.dispatcher import Dispatcher
from step4.raft_ops.raft_shim import RaftShim

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SetupHelper(SetupHelperAPI):

    def __init__(self):
        self.port = None
        
    async def get_client(self, host='127.0.0.1', port='50051'):
        proxy = await self.get_proxy(host=host, port=port)
        return Client(server_proxy=proxy)

    async def get_proxy(self, host='127.0.0.1', port='50051'):
        return ServerProxy(host, port)

    async def get_server(self, db_file: os.PathLike, port='50051'):
        self.port = port
        ops = Ops(db_file)
        dispatcher = Dispatcher(ops)
        handler = RaftShim(dispatcher)
        collector = Collector(handler)
        return BankingServiceImpl(collector)
    
    async def serve(self, server=None):
        grpc_server = await start_server(server, self.port)
        try:
            await grpc_server.start()
            logger.info(f"gRPC server started on port {self.port}")
            # Keep the server running
            await grpc_server.wait_for_termination()
        finally:
            await grpc_server.stop(grace=5)
            logger.info("gRPC server stopped")


async def start_server(banking_service: BankingServiceImpl, port: str):
    """Start the gRPC server"""
    # Enable asyncio debugging
    asyncio.get_event_loop().set_debug(True)
    logger.debug("Asyncio debug mode enabled")

    try:
        # Create the gRPC server
        server = await create_server('127.0.0.1', int(port), banking_service.server)
        logger.info(f"gRPC server created on 127.0.0.1:{port}")
        return server
    except Exception as e:
        logger.error(f"Failed to start gRPC server: {e}", exc_info=True)
        raise

    
