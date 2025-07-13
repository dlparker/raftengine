import os
import asyncio
import logging
from step5.base_plus.setup_helper import SetupHelperAPI
from step5.base_plus.client import Client
from step5.raft_ops.raft_server import RaftServer
from step5.raft_ops.proxy import ServerProxy
from step5.grpc.rpc_server import BankingServiceImpl, create_server
from step5.grpc.rpc_client import RPCClient

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SetupHelper(SetupHelperAPI):

    def __init__(self):
        self.port = None
        self.grpc_server = None
        self.server_task = None

    async def get_client(self, host='127.0.0.1', port='50051'):
        rpc_client = await self.get_rpc_client(host=host, port=port)
        proxy = ServerProxy(rpc_client)  # Wrap with @raft_command decorated proxy
        return Client(server_proxy=proxy)

    async def get_client_from_uri(self, uri):
        tmp = uri.split('/')
        trnsport_name = tmp[0].split(':')[0]
        if trnsport_name != "grpc":
            raise Exception(f"wrong transport specified, should be grpc, was {trnsport_name}")
        host, port = tmp[-1].split(':')
        rpc_client = await self.get_rpc_client(host, port)
        proxy = ServerProxy(rpc_client)  # Wrap with @raft_command decorated proxy
        return Client(server_proxy=proxy)
    
    async def get_rpc_client(self, host='127.0.0.1', port='50051'):
        return RPCClient(host, port)

    async def get_raft_server(self, initial_cluster_config, local_config):
        tmp = local_config.uri.split('/')
        trnsport_name = tmp[0].split(':')[0]
        if trnsport_name != "grpc":
            raise Exception(f"wrong transport specified, should be grpc, was {trnsport_name}")
        self.port = tmp[-1].split(':')[1]
        raft_server = RaftServer(initial_cluster_config, local_config, self)
        return raft_server
    
    async def get_rpc_server(self, raft_server):
        return BankingServiceImpl(raft_server)
    
    async def start_server_task(self, rpc_server):
        self.grpc_server = await start_server(rpc_server, self.port)
        async def tasker():
            try:
                await self.grpc_server.start()
                logger.info(f"gRPC server started on port {self.port}")
                # Keep the server running
                await self.grpc_server.wait_for_termination()
            finally:
                await self.grpc_server.stop(grace=5)
                logger.info("gRPC server stopped")
        self.server_task = asyncio.create_task(tasker())

    async def stop_server_task(self):
        await self.grpc_server.stop(grace=1)
        self.grpc_server = None
        self.server_task = None
        
                               

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

    
