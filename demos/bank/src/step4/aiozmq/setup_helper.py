import os
import asyncio
import logging
import zmq
import aiozmq.rpc
from base.setup_helper import SetupHelperAPI
from base.client import Client
from base.operations import Ops
from step4.aiozmq.server import Server as RPCServer
from step4.aiozmq.proxy import ServerProxy

# Configure logging with DEBUG level for aiozmq and custom code
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
# Ensure aiozmq and zmq loggers are set to DEBUG
logging.getLogger('aiozmq').setLevel(logging.DEBUG)
logging.getLogger('zmq').setLevel(logging.DEBUG)

class SetupHelper(SetupHelperAPI):

    def __init__(self):
        port = None
        
    async def get_client(self, host='127.0.0.1', port='55555'):
        proxy = await self.get_proxy(host=host, port=port)
        return Client(server_proxy=proxy)

    async def get_proxy(self, host='127.0.0.1', port='55555'):
        return ServerProxy(host, port)

    async def get_server(self, db_file:os.PathLike, port='55555'):
        server = Ops(db_file)
        self.port = port
        return RPCServer(server)
    
    async def serve(self, server=None):
        a_server = await start_server(server, self.port)
        try:
            # Keep the server running
            await asyncio.Event().wait()
        finally:
            a_server.close()
            await a_server.wait_closed()
            logger.info("Server closed")

async def start_server(wrapper, port):

    # Import the translation table
    from base.msgpack_helpers import get_bank_translation_table

    try:
        # Start the RPC server with translation table
        translation_table = get_bank_translation_table()
        server = await aiozmq.rpc.serve_rpc(
            wrapper,
            bind=f'tcp://127.0.0.1:{port}',
            translation_table=translation_table,
            log_exceptions=True  # Log unhandled exceptions in RPC methods
        )
        logger.info("Server started on tcp://127.0.0.1:%d", port)


        return server
    except Exception as e:
        logger.error(f"Failed to start server: {e}", exc_info=True)
        context.term()
        raise

