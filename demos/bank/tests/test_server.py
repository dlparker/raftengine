import pytest
import tempfile
import os
from datetime import datetime, timedelta, date
from decimal import Decimal
from src.server import Server
from src.datatypes import AccountType


@pytest.fixture
def temp_db():
    """Create a temporary database for testing"""
    temp_fd, temp_path = tempfile.mkstemp(suffix='.db')
    os.close(temp_fd)
    yield temp_path
    # Cleanup
    if os.path.exists(temp_path):
        os.unlink(temp_path)


@pytest.fixture
def server(temp_db):
    """Setup server with temporary database"""
    server = Server()
    server.db.db_path = temp_db
    server.db.init_database()
    server.sim_datetime = datetime(2024, 1, 15, 12, 0, 0)
    return server


@pytest.mark.asyncio
async def test_create_customer_error_handling(server):
    """Test customer creation with various inputs"""
    # Test normal customer creation
    customer = await server.create_customer("Alice", "Johnson", "789 Pine St")
    assert customer.first_name == "Alice"
    assert customer.last_name == "Johnson" 
    assert customer.address == "789 Pine St"
    assert customer.cust_id == 0
    assert customer.create_time == server.sim_datetime
    assert customer.update_time == server.sim_datetime
    
    # Test second customer gets incremented ID
    customer2 = await server.create_customer("Bob", "Smith", "456 Oak Ave")
    assert customer2.cust_id == 1


@pytest.mark.asyncio
async def test_create_account_error_handling(server):
    """Test account creation with error cases"""
    # Test with non-existent customer
    with pytest.raises(ValueError, match="Customer NonExistent not found"):
        await server.create_account("NonExistent", AccountType.CHECKING)
    
    # Test with valid customer
    await server.create_customer("John", "Doe", "123 Main St")
    account = await server.create_account("Doe,John", AccountType.SAVINGS)
    
    assert account.account_type == AccountType.SAVINGS
    assert account.customer_id == "Doe,John"
    assert account.balance == Decimal('0.00')
    assert account.account_id == 0
    assert account.create_time == server.sim_datetime
    assert account.update_time == server.sim_datetime


@pytest.mark.asyncio
async def test_deposit_error_handling(server):
    """Test deposit with error cases"""
    # Test with non-existent account
    with pytest.raises(ValueError, match="Account 999 not found"):
        await server.deposit(999, Decimal('100.00'))
    
    # Test with valid account
    await server.create_customer("Jane", "Smith", "456 Oak Ave")
    account = await server.create_account("Smith,Jane", AccountType.CHECKING)
    
    balance = await server.deposit(account.account_id, Decimal('250.50'))
    assert balance == Decimal('250.50')
    
    # Verify account was updated
    updated_account = server.db.get_account(account.account_id)
    assert updated_account.balance == Decimal('250.50')


@pytest.mark.asyncio
async def test_withdraw_error_handling(server):
    """Test withdraw with error cases"""
    # Test with non-existent account
    with pytest.raises(ValueError, match="Account 999 not found"):
        await server.withdraw(999, Decimal('50.00'))
    
    # Test with valid account
    await server.create_customer("Mike", "Wilson", "789 Pine St")
    account = await server.create_account("Wilson,Mike", AccountType.SAVINGS)
    
    # Add some money first
    await server.deposit(account.account_id, Decimal('100.00'))
    
    # Test withdrawal
    balance = await server.withdraw(account.account_id, Decimal('30.00'))
    assert balance == Decimal('70.00')
    
    # Verify account was updated
    updated_account = server.db.get_account(account.account_id)
    assert updated_account.balance == Decimal('70.00')


@pytest.mark.asyncio
async def test_transfer_error_handling(server):
    """Test transfer with various error cases"""
    # Test with non-existent from account
    with pytest.raises(ValueError, match="From account 999 not found"):
        await server.transfer(999, 1, Decimal('50.00'))
    
    # Create one account for testing to account error
    await server.create_customer("Alice", "Brown", "111 First St")
    from_account = await server.create_account("Brown,Alice", AccountType.CHECKING)
    
    # Test with non-existent to account
    with pytest.raises(ValueError, match="To account 999 not found"):
        await server.transfer(from_account.account_id, 999, Decimal('50.00'))
    
    # Create second account for successful transfer
    await server.create_customer("Bob", "Green", "222 Second St")
    to_account = await server.create_account("Green,Bob", AccountType.SAVINGS)
    
    # Test transfer with insufficient funds
    result = await server.transfer(from_account.account_id, to_account.account_id, Decimal('100.00'))
    assert result is None
    
    # Add funds and test successful transfer
    await server.deposit(from_account.account_id, Decimal('200.00'))
    result = await server.transfer(from_account.account_id, to_account.account_id, Decimal('75.00'))
    
    assert result['from_balance'] == Decimal('125.00')
    assert result['to_balance'] == Decimal('75.00')
    
    # Verify both accounts were updated
    updated_from = server.db.get_account(from_account.account_id)
    updated_to = server.db.get_account(to_account.account_id)
    assert updated_from.balance == Decimal('125.00')
    assert updated_to.balance == Decimal('75.00')


@pytest.mark.asyncio
async def test_cash_check(server):
    """Test cash_check method (should behave like withdraw)"""
    await server.create_customer("Carol", "White", "333 Third St")
    account = await server.create_account("White,Carol", AccountType.CHECKING)
    
    # Add funds
    await server.deposit(account.account_id, Decimal('150.00'))
    
    # Cash a check
    balance = await server.cash_check(account.account_id, Decimal('40.00'))
    assert balance == Decimal('110.00')


@pytest.mark.asyncio
async def test_list_accounts(server):
    """Test listing all accounts"""
    # Initially empty
    accounts = await server.list_accounts()
    assert len(accounts) == 0
    
    # Create some accounts
    await server.create_customer("Dave", "Black", "444 Fourth St")
    await server.create_customer("Eve", "Gray", "555 Fifth St")
    
    account1 = await server.create_account("Black,Dave", AccountType.CHECKING)
    account2 = await server.create_account("Gray,Eve", AccountType.SAVINGS)
    
    accounts = await server.list_accounts()
    assert len(accounts) == 2
    account_ids = [acc.account_id for acc in accounts]
    assert account1.account_id in account_ids
    assert account2.account_id in account_ids


@pytest.mark.asyncio
async def test_get_accounts_error_handling(server):
    """Test get_accounts with error cases"""
    # Test with non-existent customer
    with pytest.raises(ValueError, match="Customer NonExistent not found"):
        await server.get_accounts("NonExistent")
    
    # Test with valid customer
    await server.create_customer("Frank", "Blue", "666 Sixth St")
    await server.create_account("Blue,Frank", AccountType.CHECKING)
    await server.create_account("Blue,Frank", AccountType.SAVINGS)
    
    account_ids = await server.get_accounts("Blue,Frank")
    assert len(account_ids) == 2


@pytest.mark.asyncio
async def test_list_statements(server):
    """Test list_statements method"""
    await server.create_customer("Grace", "Red", "777 Seventh St")
    account = await server.create_account("Red,Grace", AccountType.CHECKING)
    
    # Initially no statements
    statements = await server.list_statements(account.account_id)
    assert len(statements) == 0


@pytest.mark.asyncio
async def test_advance_time_no_boundary(server):
    """Test advance_time without crossing month boundary"""
    original_time = server.sim_datetime
    
    # Advance by 5 days within same month
    await server.advance_time(timedelta(days=5))
    
    expected_time = original_time + timedelta(days=5)
    assert server.sim_datetime == expected_time


@pytest.mark.asyncio
async def test_generate_account_statement_no_transactions(server):
    """Test statement generation for account with no transactions"""
    await server.create_customer("Henry", "Purple", "888 Eighth St")
    account = await server.create_account("Purple,Henry", AccountType.SAVINGS)
    
    # Generate statement manually for testing
    start_date = date(2024, 1, 1)
    end_date = date(2024, 1, 31)
    
    await server._generate_account_statement(account, start_date, end_date)
    
    # Verify statement was created
    statements = await server.list_statements(account.account_id)
    assert len(statements) == 1
    assert statements[0] == end_date


@pytest.mark.asyncio
async def test_year_boundary_crossing(server):
    """Test month boundary detection across year boundary"""
    # Test December to January
    old_dt = datetime(2023, 12, 31, 23, 0, 0)
    new_dt = datetime(2024, 1, 1, 1, 0, 0)
    
    assert server._crosses_month_boundary(old_dt, new_dt) == True
    
    # Test that December 30 to December 31 doesn't cross
    old_dt = datetime(2023, 12, 30, 12, 0, 0)
    new_dt = datetime(2023, 12, 31, 12, 0, 0)
    
    assert server._crosses_month_boundary(old_dt, new_dt) == False


@pytest.mark.asyncio
async def test_transaction_recording(server):
    """Test that transactions are properly recorded"""
    await server.create_customer("Ivy", "Orange", "999 Ninth St")
    account = await server.create_account("Orange,Ivy", AccountType.CHECKING)
    
    # Make some transactions
    await server.deposit(account.account_id, Decimal('100.00'))
    await server.withdraw(account.account_id, Decimal('25.00'))
    
    # Get transactions from database
    transactions = server.db.get_transactions_for_period(
        account.account_id, 
        date(2024, 1, 1), 
        date(2024, 1, 31)
    )
    
    assert len(transactions) == 2
    assert transactions[0].change == Decimal('100.00')  # deposit
    assert transactions[1].change == Decimal('-25.00')  # withdrawal
    assert all(t.transaction_time.date() == server.sim_datetime.date() for t in transactions)