#!/usr/bin/env python
"""Integration tests for step2 transport components"""
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
from base.client import Client
from base.datatypes import AccountType, Customer, Account

# Import helpers for testing optional dependencies
def check_dependency(module_name):
    """Check if a module is available"""
    try:
        __import__(module_name)
        return True
    except ImportError:
        return False

# Check available transports
HAS_AIOZMQ = check_dependency('aiozmq')
HAS_FASTAPI = check_dependency('fastapi')
HAS_GRPC = check_dependency('grpc')

def get_free_port():
    """Get a free port for testing"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

@pytest.mark.integration
@pytest.mark.asyncio
class TestStep2Integration:
    """Integration tests for step2 component composition"""
    
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
    
    @pytest.mark.skipif(not HAS_AIOZMQ, reason="aiozmq not installed")
    async def test_aiozmq_component_initialization(self):
        """Test that aiozmq step2 components initialize correctly"""
        from step2.aiozmq.setup_helper import SetupHelper
        from step2.aiozmq.proxy import ServerProxy
        from step2.aiozmq.server import Server as RPCServer
        
        port = get_free_port()
        setup_helper = SetupHelper()
        
        # Test server creation
        server = await setup_helper.get_server(db_file=self.db_path, port=str(port))
        assert isinstance(server, RPCServer)
        
        # Test proxy creation
        proxy = await setup_helper.get_proxy(host='127.0.0.1', port=str(port))
        assert isinstance(proxy, ServerProxy)
        
        # Test client creation
        client = await setup_helper.get_client(host='127.0.0.1', port=str(port))
        assert isinstance(client, Client)
        assert isinstance(client.server_proxy, ServerProxy)
    
    @pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed")
    async def test_fastapi_component_initialization(self):
        """Test that FastAPI step2 components initialize correctly"""
        from step2.fastapi.setup_helper import SetupHelper
        from step2.fastapi.proxy import ServerProxy
        
        port = get_free_port()
        setup_helper = SetupHelper()
        
        # Test server creation
        server = await setup_helper.get_server(db_file=self.db_path, port=str(port))
        assert isinstance(server, Ops)  # Returns base Ops for FastAPI
        
        # Test proxy creation
        proxy = await setup_helper.get_proxy(host='127.0.0.1', port=str(port))
        assert isinstance(proxy, ServerProxy)
        
        # Test client creation
        client = await setup_helper.get_client(host='127.0.0.1', port=str(port))
        assert isinstance(client, Client)
        assert isinstance(client.server_proxy, ServerProxy)
    
    @pytest.mark.skipif(not HAS_GRPC, reason="grpcio not installed")
    async def test_grpc_component_initialization(self):
        """Test that gRPC step2 components initialize correctly"""
        from step2.grpc.setup_helper import SetupHelper
        from step2.grpc.proxy import ServerProxy
        from step2.grpc.server import BankingServiceImpl
        
        port = get_free_port()
        setup_helper = SetupHelper()
        
        # Test server creation
        server = await setup_helper.get_server(db_file=self.db_path, port=str(port))
        assert isinstance(server, BankingServiceImpl)
        
        # Test proxy creation
        proxy = await setup_helper.get_proxy(host='127.0.0.1', port=str(port))
        assert isinstance(proxy, ServerProxy)
        
        # Test client creation
        client = await setup_helper.get_client(host='127.0.0.1', port=str(port))
        assert isinstance(client, Client)
        assert isinstance(client.server_proxy, ServerProxy)
    
    @pytest.mark.skipif(not HAS_AIOZMQ, reason="aiozmq not installed")
    async def test_aiozmq_banking_workflow(self):
        """Test complete banking workflow through aiozmq transport"""
        from step2.aiozmq.setup_helper import SetupHelper
        
        port = get_free_port()
        setup_helper = SetupHelper()
        
        # Start server
        await self.start_server_background(setup_helper, port)
        
        # Create client
        client = await setup_helper.get_client(host='127.0.0.1', port=str(port))
        
        # Test basic banking operations
        customer = await client.create_customer("John", "Smith", "123 Main St")
        assert customer.first_name == "John"
        
        account = await client.create_account("Smith,John", AccountType.CHECKING)
        assert account.account_type == AccountType.CHECKING
        
        balance = await client.deposit(account.account_id, Decimal('1000.00'))
        assert balance == Decimal('1000.00')
        
        balance = await client.withdraw(account.account_id, Decimal('100.00'))
        assert balance == Decimal('900.00')
        
        accounts = await client.list_accounts()
        assert len(accounts) == 1
        assert accounts[0].balance == Decimal('900.00')
    
    @pytest.mark.skipif(not HAS_GRPC, reason="grpcio not installed")
    async def test_grpc_banking_workflow(self):
        """Test complete banking workflow through gRPC transport"""
        from step2.grpc.setup_helper import SetupHelper
        
        port = get_free_port()
        setup_helper = SetupHelper()
        
        # Start server
        await self.start_server_background(setup_helper, port)
        
        # Give gRPC server more time to start
        await asyncio.sleep(1.0)
        
        # Create client
        client = await setup_helper.get_client(host='127.0.0.1', port=str(port))
        
        # Test basic banking operations
        customer = await client.create_customer("Jane", "Doe", "456 Oak St")
        assert customer.first_name == "Jane"
        
        account = await client.create_account("Doe,Jane", AccountType.SAVINGS)
        assert account.account_type == AccountType.SAVINGS
        
        balance = await client.deposit(account.account_id, Decimal('500.00'))
        assert balance == Decimal('500.00')
        
        balance = await client.withdraw(account.account_id, Decimal('50.00'))
        assert balance == Decimal('450.00')
        
        accounts = await client.list_accounts()
        assert len(accounts) == 1
        assert accounts[0].balance == Decimal('450.00')
    
    @pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed")
    async def test_fastapi_banking_workflow(self):
        """Test complete banking workflow through FastAPI transport"""
        from step2.fastapi.setup_helper import SetupHelper
        
        port = get_free_port()
        setup_helper = SetupHelper()
        
        # Start server
        await self.start_server_background(setup_helper, port)
        
        # Give FastAPI server more time to start
        await asyncio.sleep(1.0)
        
        # Create client
        client = await setup_helper.get_client(host='127.0.0.1', port=str(port))
        
        # Test basic banking operations
        customer = await client.create_customer("Alice", "Johnson", "789 Pine St")
        assert customer.first_name == "Alice"
        
        account = await client.create_account("Johnson,Alice", AccountType.CHECKING)
        assert account.account_type == AccountType.CHECKING
        
        balance = await client.deposit(account.account_id, Decimal('750.00'))
        assert balance == Decimal('750.00')
        
        balance = await client.withdraw(account.account_id, Decimal('75.00'))
        assert balance == Decimal('675.00')
        
        accounts = await client.list_accounts()
        assert len(accounts) == 1
        assert accounts[0].balance == Decimal('675.00')
    
    @pytest.mark.skipif(not HAS_AIOZMQ, reason="aiozmq not installed")
    async def test_aiozmq_error_handling(self):
        """Test error handling through aiozmq transport"""
        from step2.aiozmq.setup_helper import SetupHelper
        
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
    
    @pytest.mark.skipif(not HAS_GRPC, reason="grpcio not installed")
    async def test_grpc_error_handling(self):
        """Test error handling through gRPC transport"""
        from step2.grpc.setup_helper import SetupHelper
        
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
    
    @pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed")
    async def test_fastapi_error_handling(self):
        """Test error handling through FastAPI transport"""
        from step2.fastapi.setup_helper import SetupHelper
        
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

@pytest.mark.integration
class TestStep2AvailableTransports:
    """Test to show which step2 transports are available"""
    
    def test_transport_availability(self):
        """Show which transports are available for testing"""
        transports = {
            'aiozmq': HAS_AIOZMQ,
            'fastapi_jsonrpc': HAS_FASTAPI,
            'grpc': HAS_GRPC
        }
        
        available = [name for name, available in transports.items() if available]
        unavailable = [name for name, available in transports.items() if not available]
        
        print(f"\nAvailable step2 transports: {available}")
        print(f"Unavailable step2 transports: {unavailable}")
        
        # At least show the transport status
        assert isinstance(transports, dict)
        assert len(transports) == 3