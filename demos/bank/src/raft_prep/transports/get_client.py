#!/usr/bin/env python
"""Client factory functions for different transport no_raft"""
from pathlib import Path
import sys

# Add the top-level directory to the path
top_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(top_dir))

from src.base.client import Client
from src.base.server import Server
from src.no_raft.transports import ASClient, ServerProxy as ASServerProxy
from src.no_raft.transports import RaftServerProxy as RaftASServerProxy
from src.no_raft.transports import RaftClient as RaftASClient
from src.no_raft.transports import GrpcServerProxy


def get_direct_client(database_file: str):
    """Create a direct client that bypasses any proxy/transport layer"""
    server = Server(db_file=database_file)
    client = Client(server)
    return client, None  # No cleanup needed


def get_astream_client(host: str, port: int):
    """Create an async streams client"""
    as_client = ASClient(host, port)
    proxy = ASServerProxy(as_client)
    client = Client(proxy)
    
    async def cleanup():
        await as_client.close()
    
    return client, cleanup


def get_raft_astream_client(host: str, port: int):
    """Create an async streams client"""
    as_client = ASClient(host, port)
    proxy = RaftASServerProxy(as_client)
    client = RaftASClient(proxy)
    
    async def cleanup():
        await as_client.close()
    
    return client, cleanup


def get_grpc_client(host: str, port: int):
    """Create a gRPC client"""
    server_address = f"{host}:{port}"
    proxy = GrpcServerProxy(server_address)
    client = Client(proxy)
    
    def cleanup():
        proxy.close()
    
    return client, cleanup
