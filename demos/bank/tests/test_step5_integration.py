#!/usr/bin/env python
"""Integration tests for step5 transport components"""
import pytest
import asyncio
import tempfile
import os
import sys
import time
import socket
from pathlib import Path
from decimal import Decimal
from datetime import timedelta

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from base.operations import Ops
from base.datatypes import AccountType, Customer, Account
# Import step5 client instead of base client for step5 tests
from step5.base_plus.client import Client
from banking_workflow_helper import validate_banking_workflow

# Import helpers for testing dependencies
def require_dependency(module_name):
    """Check if a module is available, raise ImportError if not"""
    try:
        __import__(module_name)
    except ImportError:
        raise ImportError(f"Required dependency '{module_name}' is not installed. Install it to run this step5 integration test.")

def get_free_port():
    """Get a free port for testing"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

@pytest.mark.integration
@pytest.mark.asyncio
class TestStep5Integration:
    """Integration tests for step5 component composition"""
    
    def setup_method(self):
        """Set up test database for each test"""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        self.db_path = Path(self.temp_db.name)
        self.server_task = None
        self.server_instance = None
        
    def teardown_method(self):
        """Clean up test database and server after each test"""
        if self.db_path.exists():
            os.unlink(self.db_path)
        
        # Cancel server task if it's still running
        if self.server_task and not self.server_task.done():
            try:
                self.server_task.cancel()
            except RuntimeError:
                # Event loop may already be closed, ignore
                pass
    
    async def start_server_background(self, setup_helper, port):
        """Start server in background for testing"""
        server = await setup_helper.get_server(db_file=self.db_path, port=str(port))
        self.server_instance = server
        
        # Start server in background
        self.server_task = asyncio.create_task(setup_helper.serve(server))
        
        # Give server time to start
        await asyncio.sleep(0.5)
        return server
    
    async def test_aiozmq_component_initialization(self):
        """Test that aiozmq step5 components initialize correctly"""
        require_dependency('aiozmq')
        from step5.aiozmq.setup_helper import SetupHelper
        from step5.aiozmq.proxy import ServerProxy
        
        port = get_free_port()
        setup_helper = SetupHelper()
        
        # Test server creation - check that it returns something that can be served
        server = await setup_helper.get_server(db_file=self.db_path, port=str(port))
        assert server is not None
        assert hasattr(server, '__class__')  # Basic sanity check
        
        # Test proxy creation
        proxy = await setup_helper.get_proxy(host='127.0.0.1', port=str(port))
        assert isinstance(proxy, ServerProxy)
        
        # Test client creation
        client = await setup_helper.get_client(host='127.0.0.1', port=str(port))
        assert isinstance(client, Client)
        assert isinstance(client.server_proxy, ServerProxy)
    
    async def test_fastapi_component_initialization(self):
        """Test that FastAPI step5 components initialize correctly"""
        require_dependency('fastapi')
        from step5.fastapi.setup_helper import SetupHelper
        from step5.fastapi.proxy import ServerProxy
        from step5.raft_ops.collector import Collector

        port = get_free_port()
        setup_helper = SetupHelper()
        
        # Test server creation - should return Collector for FastAPI
        server = await setup_helper.get_server(db_file=self.db_path, port=str(port))
        assert isinstance(server, Collector)
        
        # Test proxy creation
        proxy = await setup_helper.get_proxy(host='127.0.0.1', port=str(port))
        assert isinstance(proxy, ServerProxy)
        
        # Test client creation
        client = await setup_helper.get_client(host='127.0.0.1', port=str(port))
        assert isinstance(client, Client)
        assert isinstance(client.server_proxy, ServerProxy)
    
    async def test_grpc_component_initialization(self):
        """Test that gRPC step5 components initialize correctly"""
        require_dependency('grpc')
        from step5.grpc.setup_helper import SetupHelper
        from step5.grpc.rpc_client import RPCClient
        from step5.grpc.rpc_server import BankingServiceImpl
        
        port = get_free_port()
        setup_helper = SetupHelper()
        
        # Test server creation - should return BankingServiceImpl wrapping the collector
        server = await setup_helper.get_server(db_file=self.db_path, port=str(port))
        assert isinstance(server, BankingServiceImpl)
        # Verify it has the expected server attribute (the Collector)
        assert hasattr(server, 'server')
        
        # Test proxy creation
        proxy = await setup_helper.get_rpc_client(host='127.0.0.1', port=str(port))
        assert isinstance(proxy, RPCClient)
        
        # Test client creation
        client = await setup_helper.get_client(host='127.0.0.1', port=str(port))
        assert isinstance(client, Client)
        assert isinstance(client.server_proxy, RPCClient)
    
    async def test_aiozmq_banking_workflow(self):
        """Test complete banking workflow through aiozmq transport"""
        require_dependency('aiozmq')
        from step5.aiozmq.setup_helper import SetupHelper
        
        port = get_free_port()
        setup_helper = SetupHelper()
        
        # Start server
        await self.start_server_background(setup_helper, port)
        
        # Create client
        client = await setup_helper.get_client(host='127.0.0.1', port=str(port))
        
        # Run comprehensive banking test
        await validate_banking_workflow(client)
    
    async def test_grpc_banking_workflow(self):
        """Test complete banking workflow through gRPC transport"""
        require_dependency('grpc')
        from step5.grpc.setup_helper import SetupHelper
        
        port = get_free_port()
        setup_helper = SetupHelper()
        
        # Start server
        await self.start_server_background(setup_helper, port)
        
        # Give gRPC server more time to start
        await asyncio.sleep(1.0)
        
        # Create client
        client = await setup_helper.get_client(host='127.0.0.1', port=str(port))
        
        # Run comprehensive banking test
        await validate_banking_workflow(client)
    
    async def test_fastapi_banking_workflow(self):
        """Test complete banking workflow through FastAPI transport"""
        require_dependency('fastapi')
        from step5.fastapi.setup_helper import SetupHelper
        
        port = get_free_port()
        setup_helper = SetupHelper()
        
        # Start server
        await self.start_server_background(setup_helper, port)
        
        # Give FastAPI server more time to start
        await asyncio.sleep(1.0)
        
        # Create client
        client = await setup_helper.get_client(host='127.0.0.1', port=str(port))
        
        # Run comprehensive banking test
        await validate_banking_workflow(client)
    
    async def test_aiozmq_error_handling(self):
        """Test error handling through aiozmq transport"""
        require_dependency('aiozmq')
        from step5.aiozmq.setup_helper import SetupHelper
        
        port = get_free_port()
        setup_helper = SetupHelper()
        
        # Start server
        await self.start_server_background(setup_helper, port)
        
        # Create client
        client = await setup_helper.get_client(host='127.0.0.1', port=str(port))
        
        # Test operations on non-existent entities
        with pytest.raises(Exception):  # aiozmq may wrap exceptions differently
            await client.create_account("nonexistent", AccountType.CHECKING)
        
        with pytest.raises(Exception):
            await client.deposit(999, Decimal('100.00'))
    
    async def test_grpc_error_handling(self):
        """Test error handling through gRPC transport"""
        require_dependency('grpc')
        from step5.grpc.setup_helper import SetupHelper
        
        port = get_free_port()
        setup_helper = SetupHelper()
        
        # Start server
        await self.start_server_background(setup_helper, port)
        await asyncio.sleep(1.0)  # Give gRPC more startup time
        
        # Create client
        client = await setup_helper.get_client(host='127.0.0.1', port=str(port))
        
        # Test operations on non-existent entities
        with pytest.raises(Exception):  # gRPC may wrap exceptions differently
            await client.create_account("nonexistent", AccountType.CHECKING)
        
        with pytest.raises(Exception):
            await client.deposit(999, Decimal('100.00'))
    
    async def test_fastapi_error_handling(self):
        """Test error handling through FastAPI transport"""
        require_dependency('fastapi')
        from step5.fastapi.setup_helper import SetupHelper
        
        port = get_free_port()
        setup_helper = SetupHelper()
        
        # Start server
        await self.start_server_background(setup_helper, port)
        await asyncio.sleep(1.0)  # Give FastAPI more startup time
        
        # Create client
        client = await setup_helper.get_client(host='127.0.0.1', port=str(port))
        
        # Test operations on non-existent entities
        with pytest.raises(Exception):  # FastAPI/JSON-RPC may wrap exceptions differently
            await client.create_account("nonexistent", AccountType.CHECKING)
        
        with pytest.raises(Exception):
            await client.deposit(999, Decimal('100.00'))

