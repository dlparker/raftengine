#!/usr/bin/env python
"""Integration tests for step3 transport components"""
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
from banking_workflow_helper import validate_banking_workflow

def get_free_port():
    """Get a free port for testing"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

@pytest.mark.integration
@pytest.mark.asyncio
class TestStep3Integration:
    """Integration tests for step3 component composition"""
    
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
        server = await setup_helper.get_server(db_file=self.db_path, port=port)
        self.server_instance = server
        
        # Start server in background
        self.server_task = asyncio.create_task(setup_helper.serve(server))
        
        # Give server time to start
        await asyncio.sleep(0.5)
        return server
    
    async def test_direct_component_initialization(self):
        """Test that direct step3 components initialize correctly"""
        from step3.direct.setup_helper import SetupHelper
        from step3.direct.proxy import ServerProxy
        from step3.direct.collector import Collector
        from step3.direct.dispatcher import Dispatcher
        from step3.direct.command_handler import CommandHandler
        
        setup_helper = SetupHelper()
        assert setup_helper is not None
        
        # Test server creation (Operations)
        server = await setup_helper.get_server(db_file=self.db_path)
        assert isinstance(server, Ops)
        
        # Test proxy creation
        proxy = await setup_helper.get_proxy(server=server)
        assert isinstance(proxy, ServerProxy)
        assert isinstance(proxy.collector, Collector)
        
        # Test client creation
        client = await setup_helper.get_client(db_file=self.db_path)
        assert isinstance(client, Client)
        assert isinstance(client.server_proxy, ServerProxy)
    
    async def test_astream_component_initialization(self):
        """Test that astream step3 components initialize correctly"""
        from step3.astream.setup_helper import SetupHelper
        from step3.astream.proxy import ServerProxy
        from step3.astream.collector import Collector
        from step3.astream.dispatcher import Dispatcher
        from step3.astream.as_client import ASClient
        
        port = get_free_port()
        setup_helper = SetupHelper()
        
        # Test server creation
        server = await setup_helper.get_server(db_file=self.db_path, port=port)
        assert server is not None  # AsyncIO server
        
        # Test proxy creation
        proxy = await setup_helper.get_proxy(host='127.0.0.1', port=port)
        assert isinstance(proxy, Collector)  # In step3 astream, proxy returns collector directly
        assert isinstance(proxy.as_client, ASClient)
        
        # Test client creation
        client = await setup_helper.get_client(host='127.0.0.1', port=port)
        assert isinstance(client, Client)
        assert isinstance(client.server_proxy, Collector)
    
    async def test_direct_banking_workflow(self):
        """Test full banking workflow through step3 direct components"""
        from step3.direct.setup_helper import SetupHelper
        
        setup_helper = SetupHelper()
        client = await setup_helper.get_client(db_file=self.db_path)
        
        # Run the standard banking workflow test
        await validate_banking_workflow(client)
    
    async def test_astream_banking_workflow(self):
        """Test full banking workflow through step3 astream components"""
        from step3.astream.setup_helper import SetupHelper
        
        port = get_free_port()
        setup_helper = SetupHelper()
        
        # Start server in background
        await self.start_server_background(setup_helper, port)
        
        # Create client and run tests
        client = await setup_helper.get_client(host='127.0.0.1', port=port)
        
        # Run the standard banking workflow test
        await validate_banking_workflow(client)
    
    async def test_direct_command_serialization(self):
        """Test that commands are properly serialized/deserialized in direct mode"""
        from step3.direct.setup_helper import SetupHelper
        from step3.direct.collector import Collector
        from step3.direct.dispatcher import Dispatcher
        from base.datatypes import CommandType
        from base.json_helpers import bank_json_dumps, bank_json_loads
        
        setup_helper = SetupHelper()
        client = await setup_helper.get_client(db_file=self.db_path)
        
        # Create a customer to test command serialization
        customer = await client.create_customer("Serialize", "Test", "123 Command St")
        
        # Verify the customer was created (command was serialized and executed)
        assert customer.first_name == "Serialize"
        assert customer.last_name == "Test"
        assert customer.address == "123 Command St"
        assert customer.cust_id == 0  # First customer
    
    async def test_astream_command_serialization(self):
        """Test that commands are properly serialized/deserialized through astream"""
        from step3.astream.setup_helper import SetupHelper
        
        port = get_free_port()
        setup_helper = SetupHelper()
        
        # Start server in background
        await self.start_server_background(setup_helper, port)
        
        client = await setup_helper.get_client(host='127.0.0.1', port=port)
        
        # Create a customer to test command serialization over network
        customer = await client.create_customer("Network", "Test", "456 Stream St")
        
        # Verify the customer was created (command was serialized, sent over TCP, and executed)
        assert customer.first_name == "Network"
        assert customer.last_name == "Test"
        assert customer.address == "456 Stream St"
        assert customer.cust_id == 0  # First customer
    
    async def test_direct_error_handling(self):
        """Test error handling in step3 direct components (errors pass through)"""
        from step3.direct.setup_helper import SetupHelper
        
        setup_helper = SetupHelper()
        client = await setup_helper.get_client(db_file=self.db_path)
        
        # Test withdraw from non-existent account (should pass through from Operations)
        with pytest.raises(ValueError, match="Account .* not found"):
            await client.withdraw(999, Decimal('100.00'))
        
        # Test create account for non-existent customer (should pass through from Operations)
        with pytest.raises(ValueError, match="Customer .* not found"):
            await client.create_account("NonExistent,Customer", AccountType.CHECKING)
    
    async def test_direct_insufficient_funds_transfer(self):
        """Test insufficient funds handling in step3 direct components"""
        from step3.direct.setup_helper import SetupHelper
        
        setup_helper = SetupHelper()
        client = await setup_helper.get_client(db_file=self.db_path)
        
        # Create customer and accounts
        customer = await client.create_customer("Test", "User", "123 Test St")
        checking = await client.create_account("User,Test", AccountType.CHECKING)
        savings = await client.create_account("User,Test", AccountType.SAVINGS)
        
        # Deposit some money
        await client.deposit(checking.account_id, Decimal('50.00'))
        
        # Try to transfer more than available
        result = await client.transfer(checking.account_id, savings.account_id, Decimal('100.00'))
        assert result is None  # Should return None for insufficient funds
    
    async def test_astream_insufficient_funds_transfer(self):
        """Test insufficient funds handling in step3 astream components"""
        from step3.astream.setup_helper import SetupHelper
        
        port = get_free_port()
        setup_helper = SetupHelper()
        
        # Start server in background
        await self.start_server_background(setup_helper, port)
        
        client = await setup_helper.get_client(host='127.0.0.1', port=port)
        
        # Create customer and accounts
        customer = await client.create_customer("Test", "User", "123 Test St")
        checking = await client.create_account("User,Test", AccountType.CHECKING)
        savings = await client.create_account("User,Test", AccountType.SAVINGS)
        
        # Deposit some money
        await client.deposit(checking.account_id, Decimal('50.00'))
        
        # Try to transfer more than available
        result = await client.transfer(checking.account_id, savings.account_id, Decimal('100.00'))
        assert result is None  # Should return None for insufficient funds
    
    async def test_direct_database_persistence(self):
        """Test database persistence in step3 direct components"""
        from step3.direct.setup_helper import SetupHelper
        
        setup_helper = SetupHelper()
        
        # Create first client and add data
        client1 = await setup_helper.get_client(db_file=self.db_path)
        customer = await client1.create_customer("Persistent", "User", "456 Save St")
        account = await client1.create_account("User,Persistent", AccountType.SAVINGS)
        await client1.deposit(account.account_id, Decimal('1000.00'))
        
        # Create second client (new instance, same database)
        client2 = await setup_helper.get_client(db_file=self.db_path)
        accounts = await client2.list_accounts()
        
        # Verify data persisted
        assert len(accounts) == 1
        assert accounts[0].customer_id == "User,Persistent"
        assert accounts[0].balance == Decimal('1000.00')
    
    async def test_direct_component_isolation(self):
        """Test that step3 direct components are properly isolated"""
        from step3.direct.setup_helper import SetupHelper
        from step3.direct.collector import Collector
        from step3.direct.dispatcher import Dispatcher
        
        setup_helper = SetupHelper()
        
        # Create two separate client instances
        client1 = await setup_helper.get_client(db_file=self.db_path)
        client2 = await setup_helper.get_client(db_file=self.db_path)
        
        # Verify they have different collectors but same underlying operations
        collector1 = client1.server_proxy.collector
        collector2 = client2.server_proxy.collector
        
        assert isinstance(collector1, Collector)
        assert isinstance(collector2, Collector)
        assert collector1 is not collector2  # Different collector instances
        
        # But they should share the same database
        customer1 = await client1.create_customer("Shared", "Customer", "789 DB St")
        accounts = await client2.list_accounts()  # Should see customer created by client1
        assert len(accounts) == 0  # No accounts yet, but customer exists in shared DB