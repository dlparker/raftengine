import pytest
import tempfile
import os
from decimal import Decimal
from datetime import timedelta, date
from src.base.client import Client
from src.transports.direct.proxy import ServerProxy, ServerWrapper
from src.base.server import Server
from src.base.datatypes import AccountType, Customer, Account


class TestIntegrationFlow:
    """Test the complete flow from Client through ServerProxy, ServerWrapper to Server"""
    
    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database file for testing"""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        yield path
        if os.path.exists(path):
            os.unlink(path)
    
    @pytest.fixture
    def full_stack(self, temp_db_path):
        """Create the complete Client->Proxy->Wrapper->Server stack"""
        server = Server()
        # Override the database path to use our temporary file
        server.db.db_path = temp_db_path
        server.db.init_database()
        
        wrapper = ServerWrapper(server)
        proxy = ServerProxy(wrapper)
        client = Client(proxy)
        
        return client, proxy, wrapper, server
    
    @pytest.mark.asyncio
    async def test_create_customer_full_flow(self, full_stack):
        """Test customer creation through the complete stack"""
        client, proxy, wrapper, server = full_stack
        
        # Test through client
        customer = await client.create_customer("John", "Doe", "123 Main St")
        
        assert isinstance(customer, Customer)
        assert customer.first_name == "John"
        assert customer.last_name == "Doe"
        assert customer.address == "123 Main St"
        assert customer.cust_id == 0
        assert customer.accounts == []
        assert customer.create_time is not None
        assert customer.update_time is not None
        
        # Verify it's actually stored in the server's database
        stored_customer = server.db.get_customer("Doe,John")
        assert stored_customer is not None
        assert stored_customer.first_name == "John"
        assert stored_customer.last_name == "Doe"
    
    @pytest.mark.asyncio
    async def test_create_account_full_flow(self, full_stack):
        """Test account creation through the complete stack"""
        client, proxy, wrapper, server = full_stack
        
        # First create a customer
        customer = await client.create_customer("Jane", "Smith", "456 Oak Ave")
        
        # Create checking account through client
        account = await client.create_account("Smith,Jane", AccountType.CHECKING)
        
        assert isinstance(account, Account)
        assert account.account_type == AccountType.CHECKING
        assert account.customer_id == "Smith,Jane"
        assert account.balance == Decimal('0.00')
        assert account.account_id == 0
        
        # Verify it's stored in server's database
        stored_account = server.db.get_account(0)
        assert stored_account is not None
        assert stored_account.account_type == AccountType.CHECKING
        assert stored_account.customer_id == "Smith,Jane"
        
        # Verify customer's accounts list is updated
        updated_customer = server.db.get_customer("Smith,Jane")
        assert 0 in updated_customer.accounts
    
    @pytest.mark.asyncio
    async def test_banking_operations_full_flow(self, full_stack):
        """Test deposit, withdraw, and transfer through complete stack"""
        client, proxy, wrapper, server = full_stack
        
        # Setup: create customer and accounts
        customer = await client.create_customer("Bob", "Wilson", "789 Pine St")
        checking = await client.create_account("Wilson,Bob", AccountType.CHECKING)
        savings = await client.create_account("Wilson,Bob", AccountType.SAVINGS)
        
        # Test deposit through client
        balance = await client.deposit(checking.account_id, Decimal('1000.00'))
        assert balance == Decimal('1000.00')
        
        # Verify transaction recorded
        transactions = server.db.get_all_transactions()
        assert len(transactions) == 1
        assert transactions[0].account_id == checking.account_id
        assert transactions[0].change == Decimal('1000.00')
        
        # Test withdrawal through client
        balance = await client.withdraw(checking.account_id, Decimal('250.00'))
        assert balance == Decimal('750.00')
        
        # Verify second transaction recorded
        transactions = server.db.get_all_transactions()
        assert len(transactions) == 2
        assert transactions[1].change == Decimal('-250.00')
        
        # Test transfer through client
        result = await client.transfer(checking.account_id, savings.account_id, Decimal('300.00'))
        
        assert result is not None
        assert result['from_balance'] == Decimal('450.00')
        assert result['to_balance'] == Decimal('300.00')
        
        # Verify both accounts updated in database
        checking_account = server.db.get_account(checking.account_id)
        savings_account = server.db.get_account(savings.account_id)
        assert checking_account.balance == Decimal('450.00')
        assert savings_account.balance == Decimal('300.00')
        
        # Verify transfer created two transactions
        transactions = server.db.get_all_transactions()
        assert len(transactions) == 4  # deposit + withdraw + transfer_from + transfer_to
    
    @pytest.mark.asyncio
    async def test_cash_check_full_flow(self, full_stack):
        """Test cash check through complete stack"""
        client, proxy, wrapper, server = full_stack
        
        # Setup
        customer = await client.create_customer("Alice", "Brown", "321 Elm St")
        account = await client.create_account("Brown,Alice", AccountType.CHECKING)
        await client.deposit(account.account_id, Decimal('500.00'))
        
        # Test cash check (should work like withdrawal)
        balance = await client.cash_check(account.account_id, Decimal('75.00'))
        assert balance == Decimal('425.00')
        
        # Verify account updated
        stored_account = server.db.get_account(account.account_id)
        assert stored_account.balance == Decimal('425.00')
    
    @pytest.mark.asyncio
    async def test_list_operations_full_flow(self, full_stack):
        """Test list accounts and get accounts through complete stack"""
        client, proxy, wrapper, server = full_stack
        
        # Setup multiple customers and accounts
        customer1 = await client.create_customer("Tom", "Jones", "111 First St")
        customer2 = await client.create_customer("Sue", "Davis", "222 Second St")
        
        account1 = await client.create_account("Jones,Tom", AccountType.CHECKING)
        account2 = await client.create_account("Jones,Tom", AccountType.SAVINGS)
        account3 = await client.create_account("Davis,Sue", AccountType.CHECKING)
        
        # Test list all accounts
        all_accounts = await client.list_accounts()
        assert len(all_accounts) == 3
        account_ids = [acc.account_id for acc in all_accounts]
        assert account1.account_id in account_ids
        assert account2.account_id in account_ids
        assert account3.account_id in account_ids
        
        # Test get specific customer's accounts
        tom_accounts = await client.get_accounts("Jones,Tom")
        assert len(tom_accounts) == 2
        assert account1.account_id in tom_accounts
        assert account2.account_id in tom_accounts
        
        sue_accounts = await client.get_accounts("Davis,Sue")
        assert len(sue_accounts) == 1
        assert account3.account_id in sue_accounts
    
    @pytest.mark.asyncio
    async def test_time_advance_and_statements_full_flow(self, full_stack):
        """Test time advancement and statement generation through complete stack"""
        client, proxy, wrapper, server = full_stack
        
        # Setup
        customer = await client.create_customer("Mark", "Taylor", "555 Time St")
        account = await client.create_account("Taylor,Mark", AccountType.CHECKING)
        await client.deposit(account.account_id, Decimal('1000.00'))
        
        # Advance time to trigger statement generation
        await client.advance_time(timedelta(days=32))  # Cross month boundary
        
        # Check statements were generated
        statement_dates = await client.list_statements(account.account_id)
        assert len(statement_dates) > 0
        
        # Verify statements in database
        statements = server.db.get_all_statements()
        assert len(statements) > 0
        assert statements[0].account_id == account.account_id
    
    @pytest.mark.asyncio
    async def test_error_propagation_full_flow(self, full_stack):
        """Test that errors propagate correctly through all layers"""
        client, proxy, wrapper, server = full_stack
        
        # Test customer not found error
        with pytest.raises(ValueError, match="Customer NonExistent not found"):
            await client.create_account("NonExistent", AccountType.CHECKING)
        
        # Test account not found error
        with pytest.raises(ValueError, match="Account 999 not found"):
            await client.deposit(999, Decimal('100.00'))
        
        # Test invalid to_account error
        customer = await client.create_customer("Poor", "Person", "No Money St")
        account = await client.create_account("Person,Poor", AccountType.CHECKING)
        
        with pytest.raises(ValueError, match="To account 999 not found"):
            await client.transfer(account.account_id, 999, Decimal('100.00'))
        
        # Test insufficient funds (returns None, not exception)
        account2 = await client.create_account("Person,Poor", AccountType.SAVINGS)
        result = await client.transfer(account.account_id, account2.account_id, Decimal('100.00'))
        assert result is None  # Should return None for insufficient funds
    
    @pytest.mark.asyncio
    async def test_command_serialization_through_proxy(self, full_stack):
        """Test that commands are properly serialized and deserialized"""
        client, proxy, wrapper, server = full_stack
        
        # This test verifies the command pattern is working by ensuring
        # method calls with complex parameters work through the proxy
        customer = await client.create_customer("Complex", "Test", "123 Proxy St")
        
        # Create account with enum parameter
        account = await client.create_account("Test,Complex", AccountType.SAVINGS)
        assert account.account_type == AccountType.SAVINGS
        
        # Deposit with Decimal parameter
        balance = await client.deposit(account.account_id, Decimal('99.99'))
        assert balance == Decimal('99.99')
        
        # Transfer with multiple parameters
        account2 = await client.create_account("Test,Complex", AccountType.CHECKING)
        result = await client.transfer(account.account_id, account2.account_id, Decimal('50.00'))
        
        assert result is not None
        assert result['from_balance'] == Decimal('49.99')
        assert result['to_balance'] == Decimal('50.00')
    
    @pytest.mark.asyncio
    async def test_multiple_customers_isolation(self, full_stack):
        """Test that operations on different customers are properly isolated"""
        client, proxy, wrapper, server = full_stack
        
        # Create two customers with accounts
        customer1 = await client.create_customer("User", "One", "Address 1")
        customer2 = await client.create_customer("User", "Two", "Address 2")
        
        account1 = await client.create_account("One,User", AccountType.CHECKING)
        account2 = await client.create_account("Two,User", AccountType.CHECKING)
        
        # Deposit different amounts
        await client.deposit(account1.account_id, Decimal('100.00'))
        await client.deposit(account2.account_id, Decimal('200.00'))
        
        # Verify balances are isolated
        customer1_accounts = await client.get_accounts("One,User")
        customer2_accounts = await client.get_accounts("Two,User")
        
        assert account1.account_id in customer1_accounts
        assert account1.account_id not in customer2_accounts
        assert account2.account_id in customer2_accounts
        assert account2.account_id not in customer1_accounts
        
        # Verify balances in database
        stored_account1 = server.db.get_account(account1.account_id)
        stored_account2 = server.db.get_account(account2.account_id)
        assert stored_account1.balance == Decimal('100.00')
        assert stored_account2.balance == Decimal('200.00')
    
    @pytest.mark.asyncio
    async def test_async_operation_consistency(self, full_stack):
        """Test that async operations maintain data consistency"""
        client, proxy, wrapper, server = full_stack
        
        # Setup
        customer = await client.create_customer("Async", "User", "Async St")
        account = await client.create_account("User,Async", AccountType.CHECKING)
        
        # Perform multiple async operations
        await client.deposit(account.account_id, Decimal('1000.00'))
        await client.withdraw(account.account_id, Decimal('100.00'))
        await client.deposit(account.account_id, Decimal('50.00'))
        await client.withdraw(account.account_id, Decimal('25.00'))
        
        # Final balance should be 1000 - 100 + 50 - 25 = 925
        final_account = server.db.get_account(account.account_id)
        assert final_account.balance == Decimal('925.00')
        
        # Verify all transactions recorded
        transactions = server.db.get_all_transactions()
        assert len(transactions) == 4
        
        # Verify transaction amounts
        expected_changes = [Decimal('1000.00'), Decimal('-100.00'), 
                          Decimal('50.00'), Decimal('-25.00')]
        actual_changes = [t.change for t in transactions]
        assert actual_changes == expected_changes