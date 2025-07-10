#!/usr/bin/env python
"""Integration test for step1 transport components"""
import pytest
import tempfile
import os
from pathlib import Path
from decimal import Decimal
from datetime import timedelta

# Add src to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from base.operations import Ops
from base.client import Client
from base.datatypes import AccountType, Customer, Account
from step1.direct.proxy import ServerProxy
from step1.direct.setup_helper import SetupHelper


@pytest.mark.integration
@pytest.mark.asyncio
class TestStep1Integration:
    """Integration tests for step1 component composition"""
    
    def setup_method(self):
        """Set up test database for each test"""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        self.db_path = Path(self.temp_db.name)
        
    def teardown_method(self):
        """Clean up test database after each test"""
        if self.db_path.exists():
            os.unlink(self.db_path)
    
    async def test_component_initialization(self):
        """Test that all step1 components initialize correctly"""
        # Test SetupHelper can create all components
        setup_helper = SetupHelper()
        assert setup_helper is not None
        
        # Test server creation
        server = await setup_helper.get_server(db_file=self.db_path)
        assert isinstance(server, Ops)
        
        # Test proxy creation
        proxy = await setup_helper.get_proxy(server=server)
        assert isinstance(proxy, ServerProxy)
        assert proxy.server is server
        
        # Test client creation
        client = await setup_helper.get_client(db_file=self.db_path)
        assert isinstance(client, Client)
        assert isinstance(client.server_proxy, ServerProxy)
    
    async def test_full_banking_workflow(self):
        """Test complete banking workflow through step1 components"""
        # Initialize client through SetupHelper
        setup_helper = SetupHelper()
        client = await setup_helper.get_client(db_file=self.db_path)
        
        # Test customer creation
        customer = await client.create_customer("John", "Smith", "123 Main St")
        assert isinstance(customer, Customer)
        assert customer.first_name == "John"
        assert customer.last_name == "Smith"
        assert customer.cust_id == 0  # First customer
        
        # Test account creation
        checking = await client.create_account("Smith,John", AccountType.CHECKING)
        savings = await client.create_account("Smith,John", AccountType.SAVINGS)
        
        assert isinstance(checking, Account)
        assert isinstance(savings, Account)
        assert checking.account_type == AccountType.CHECKING
        assert savings.account_type == AccountType.SAVINGS
        assert checking.balance == Decimal('0.00')
        assert savings.balance == Decimal('0.00')
        
        # Test deposit
        balance = await client.deposit(checking.account_id, Decimal('1000.00'))
        assert balance == Decimal('1000.00')
        
        balance = await client.deposit(savings.account_id, Decimal('500.00'))
        assert balance == Decimal('500.00')
        
        # Test withdrawal
        balance = await client.withdraw(checking.account_id, Decimal('100.00'))
        assert balance == Decimal('900.00')
        
        # Test transfer
        result = await client.transfer(checking.account_id, savings.account_id, Decimal('200.00'))
        assert result is not None
        assert result['from_balance'] == Decimal('700.00')
        assert result['to_balance'] == Decimal('700.00')
        
        # Test cash check
        balance = await client.cash_check(checking.account_id, Decimal('50.00'))
        assert balance == Decimal('650.00')
        
        # Test list accounts
        accounts = await client.list_accounts()
        assert len(accounts) == 2
        assert any(acc.account_id == checking.account_id for acc in accounts)
        assert any(acc.account_id == savings.account_id for acc in accounts)
        
        # Test get customer accounts
        customer_accounts = await client.get_accounts("Smith,John")
        assert len(customer_accounts) == 2
        assert checking.account_id in customer_accounts
        assert savings.account_id in customer_accounts
        
        # Test list statements
        statements = await client.list_statements(checking.account_id)
        assert isinstance(statements, list)
        
        # Test advance time
        await client.advance_time(timedelta(hours=24))
        # Should not raise exception
    
    async def test_error_handling(self):
        """Test error handling through step1 components"""
        setup_helper = SetupHelper()
        client = await setup_helper.get_client(db_file=self.db_path)
        
        # Test account creation with non-existent customer
        with pytest.raises(ValueError, match="Customer nonexistent not found"):
            await client.create_account("nonexistent", AccountType.CHECKING)
        
        # Test operations on non-existent account
        with pytest.raises(ValueError, match="Account 999 not found"):
            await client.deposit(999, Decimal('100.00'))
        
        with pytest.raises(ValueError, match="Account 999 not found"):
            await client.withdraw(999, Decimal('100.00'))
        
        with pytest.raises(ValueError, match="Account 999 not found"):
            await client.cash_check(999, Decimal('100.00'))
        
        # Test get_accounts with non-existent customer
        with pytest.raises(ValueError, match="Customer nonexistent not found"):
            await client.get_accounts("nonexistent")
    
    async def test_insufficient_funds_transfer(self):
        """Test transfer with insufficient funds"""
        setup_helper = SetupHelper()
        client = await setup_helper.get_client(db_file=self.db_path)
        
        # Create customer and accounts
        customer = await client.create_customer("Jane", "Doe", "456 Oak St")
        checking = await client.create_account("Doe,Jane", AccountType.CHECKING)
        savings = await client.create_account("Doe,Jane", AccountType.SAVINGS)
        
        # Deposit small amount
        await client.deposit(checking.account_id, Decimal('50.00'))
        
        # Try to transfer more than available
        result = await client.transfer(checking.account_id, savings.account_id, Decimal('100.00'))
        assert result is None  # Should return None for insufficient funds
        
        # Verify balances unchanged
        accounts = await client.list_accounts()
        checking_account = next(acc for acc in accounts if acc.account_id == checking.account_id)
        savings_account = next(acc for acc in accounts if acc.account_id == savings.account_id)
        
        assert checking_account.balance == Decimal('50.00')
        assert savings_account.balance == Decimal('0.00')
    
    async def test_database_persistence(self):
        """Test that operations are persisted to database"""
        setup_helper = SetupHelper()
        
        # Create client and perform operations
        client1 = await setup_helper.get_client(db_file=self.db_path)
        customer = await client1.create_customer("Alice", "Johnson", "789 Pine St")
        account = await client1.create_account("Johnson,Alice", AccountType.CHECKING)
        await client1.deposit(account.account_id, Decimal('1000.00'))
        
        # Create new client with same database
        client2 = await setup_helper.get_client(db_file=self.db_path)
        accounts = await client2.list_accounts()
        
        # Verify data persisted
        assert len(accounts) == 1
        assert accounts[0].account_id == account.account_id
        assert accounts[0].balance == Decimal('1000.00')
        assert accounts[0].customer_id == "Johnson,Alice"
    
    async def test_component_isolation(self):
        """Test that components are properly isolated"""
        setup_helper = SetupHelper()
        
        # Create two separate client instances
        client1 = await setup_helper.get_client(db_file=self.db_path)
        client2 = await setup_helper.get_client(db_file=self.db_path)
        
        # They should be different instances
        assert client1 is not client2
        assert client1.server_proxy is not client2.server_proxy
        assert client1.server_proxy.server is not client2.server_proxy.server
        
        # But they should operate on the same database
        customer = await client1.create_customer("Bob", "Wilson", "321 Elm St")
        accounts = await client2.list_accounts()
        
        # client2 should see client1's changes
        assert len(accounts) == 0  # No accounts created yet
        
        account = await client1.create_account("Wilson,Bob", AccountType.CHECKING)
        accounts = await client2.list_accounts()
        assert len(accounts) == 1
    
    async def test_monthly_statement_generation(self):
        """Test monthly statement generation through time advancement"""
        setup_helper = SetupHelper()
        client = await setup_helper.get_client(db_file=self.db_path)
        
        # Create customer and account
        customer = await client.create_customer("Charlie", "Brown", "555 Maple Ave")
        account = await client.create_account("Brown,Charlie", AccountType.CHECKING)
        
        # Make some transactions
        await client.deposit(account.account_id, Decimal('1000.00'))
        await client.withdraw(account.account_id, Decimal('100.00'))
        
        # Advance time by more than a month to trigger statement generation
        await client.advance_time(timedelta(days=32))
        
        # Check statements were generated
        statements = await client.list_statements(account.account_id)
        assert len(statements) >= 1