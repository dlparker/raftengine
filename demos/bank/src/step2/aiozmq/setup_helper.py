import os
import asyncio
import logging
import zmq
import aiozmq.rpc
from base.setup_helper import SetupHelperAPI
from base.client import Client
from base.server import Server
from step2.aiozmq.server import Server as RPCServer
from step2.aiozmq.proxy import ServerProxy

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
        server = Server(db_file)
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
    # Enable asyncio debugging
    asyncio.get_event_loop().set_debug(True)
    logger.debug("Asyncio debug mode enabled")

    # Import the translation table
    from base.msgpack_helpers import get_bank_translation_table

    # Create ZeroMQ context
    context = zmq.Context()
    try:
        # Start the RPC server with translation table
        translation_table = get_bank_translation_table()
        server = await aiozmq.rpc.serve_rpc(
            wrapper,
            bind=f'tcp://127.0.0.1:{port}',
            translation_table=translation_table,
            log_exceptions=True  # Log unhandled exceptions in RPC methods
        )
        logger.info("Server started on tcp://127.0.0.1:5555")

        # Start monitoring the server's ZeroMQ socket
        socket = server.transport.get_extra_info('zmq_socket')
        asyncio.create_task(monitor_socket(socket))

        return server
    except Exception as e:
        logger.error(f"Failed to start server: {e}", exc_info=True)
        context.term()
        raise

async def monitor_socket(socket):
    """Monitor ZeroMQ socket events for debugging."""
    monitor = socket.get_monitor_socket(zmq.EVENT_ALL)
    try:
        while True:
            event = await asyncio.get_event_loop().run_in_executor(None, monitor.recv_multipart)
            event_id = int.from_bytes(event[0][:2], 'little')
            event_value = int.from_bytes(event[0][2:], 'little')
            event_types = {
                zmq.EVENT_ACCEPTED: "ACCEPTED",
                zmq.EVENT_CLOSED: "CLOSED",
                zmq.EVENT_DISCONNECTED: "DISCONNECTED",
                zmq.EVENT_HANDSHAKE_SUCCEEDED: "HANDSHAKE_SUCCEEDED",
                zmq.EVENT_HANDSHAKE_FAILED: "HANDSHAKE_FAILED"
            }
            event_name = event_types.get(event_id, f"UNKNOWN({event_id})")
            logger.debug(f"Socket event: {event_name}, value: {event_value}")
    except Exception as e:
        logger.error(f"Error in socket monitoring: {e}")
    finally:
        # Clean up the monitor socket when done
        socket.disable_monitor()
