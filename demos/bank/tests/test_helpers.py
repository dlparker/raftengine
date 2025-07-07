"""Test helper functions for different transport mechanisms"""
import asyncio
import tempfile
import os
from src.base.server import Server
from src.base.client import Client
from src.no_raft.transports.async_streams.proxy import ASServer, get_astream_client


async def setup_async_streams_test(temp_db_path: str, host: str = "127.0.0.1", port: int = 0):
    """
    Set up async streams client-server for testing
    
    Args:
        temp_db_path: Path to temporary database
        host: Server host (default: 127.0.0.1)
        port: Server port (default: 0 for auto-assign)
    
    Returns:
        tuple: (client, cleanup_func, actual_port)
    """
    # Create server
    server = Server(db_file=temp_db_path)
    as_server = ASServer(server, host, port)
    
    # Start server
    sock_server = await asyncio.start_server(
        as_server.handle_client, host, port)
    
    # Get the actual port if port=0 was used
    actual_port = sock_server.sockets[0].getsockname()[1]
    
    # Create client
    client, client_cleanup = get_astream_client(host, actual_port)
    
    async def cleanup():
        """Clean up server and client"""
        if client_cleanup:
            await client_cleanup()
        sock_server.close()
        await sock_server.wait_closed()
    
    return client, cleanup, actual_port


def create_temp_db():
    """Create a temporary database file for testing"""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    return path


def cleanup_temp_db(path: str):
    """Clean up temporary database file"""
    if os.path.exists(path):
        os.unlink(path)