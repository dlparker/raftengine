import pytest
import tempfile
import os
from datetime import datetime, timedelta, date
from decimal import Decimal
from src.base.server import Server
from src.transports.indirect.proxy import ServerProxy, ServerWrapper
from src.base.client import Client
from src.base.datatypes import AccountType


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
def banking_setup(temp_db):
    """Setup banking system components for testing"""
    server = Server()
    # Use temporary database
    server.db.db_path = temp_db
    server.db.init_database()
    
    wrapper = ServerWrapper(server)
    proxy = ServerProxy(wrapper)
    client = Client(proxy)
    
    return server, wrapper, proxy, client


@pytest.mark.asyncio
async def test_monthly_statement_generation(banking_setup):
    """Test monthly statement generation when crossing month boundaries"""
    server, wrapper, proxy, client = banking_setup
    
    # Set initial date to end of month
    server.sim_datetime = datetime(2024, 1, 30, 23, 50, 0)
    
    # Create customer and account
    customer = await client.create_customer("John", "Doe", "123 Main St")
    assert customer.first_name == "John"
    assert customer.last_name == "Doe"
    
    account = await server.create_account("Doe,John", AccountType.CHECKING)
    assert account.account_type == AccountType.CHECKING
    assert account.balance == Decimal('0.00')
    
    # Make some transactions
    await server.deposit(account.account_id, Decimal('100.00'))
    await server.withdraw(account.account_id, Decimal('25.00'))
    await server.deposit(account.account_id, Decimal('50.00'))
    
    current_account = server.db.get_account(account.account_id)
    assert current_account.balance == Decimal('125.00')
    
    # Check statements before month boundary
    statements_before = await server.list_statements(account.account_id)
    assert len(statements_before) == 0
    
    # Advance time to cross month boundary (from Jan 30 to Feb 1)
    await server.advance_time(timedelta(days=2))
    assert server.sim_datetime == datetime(2024, 2, 1, 23, 50, 0)
    
    # Check statements after month boundary
    statements_after = await server.list_statements(account.account_id)
    assert len(statements_after) == 1
    assert statements_after[0] == date(2024, 1, 31)
    
    # Make more transactions in the new month
    await server.deposit(account.account_id, Decimal('200.00'))
    await server.withdraw(account.account_id, Decimal('30.00'))
    
    # Advance time to cross another month boundary (from Feb to Mar)
    server.sim_datetime = datetime(2024, 2, 28, 23, 50, 0)
    await server.advance_time(timedelta(days=2))
    assert server.sim_datetime == datetime(2024, 3, 1, 23, 50, 0)
    
    # Check final statements
    final_statements = await server.list_statements(account.account_id)
    assert len(final_statements) == 2
    assert final_statements[0] == date(2024, 1, 31)
    assert final_statements[1] == date(2024, 2, 29)


@pytest.mark.asyncio
async def test_month_boundary_detection(banking_setup):
    """Test month boundary detection logic"""
    server, _, _, _ = banking_setup
    
    # Test December to January boundary
    server.sim_datetime = datetime(2023, 12, 31, 22, 0, 0)
    old_dt = server.sim_datetime
    new_dt = server.sim_datetime + timedelta(hours=3)  # Cross to Jan 1
    
    assert server._crosses_month_boundary(old_dt, new_dt) == True
    
    # Test within same month
    server.sim_datetime = datetime(2024, 1, 15, 12, 0, 0)
    old_dt = server.sim_datetime
    new_dt = server.sim_datetime + timedelta(days=5)  # Still in January
    
    assert server._crosses_month_boundary(old_dt, new_dt) == False
    
    # Test February to March (leap year)
    server.sim_datetime = datetime(2024, 2, 29, 23, 0, 0)
    old_dt = server.sim_datetime
    new_dt = server.sim_datetime + timedelta(hours=2)  # Cross to Mar 1
    
    assert server._crosses_month_boundary(old_dt, new_dt) == True


@pytest.mark.asyncio
async def test_statement_content_accuracy(banking_setup):
    """Test that statement content is calculated correctly"""
    server, _, _, client = banking_setup
    
    # Set to beginning of month
    server.sim_datetime = datetime(2024, 1, 1, 12, 0, 0)
    
    # Create customer and account
    customer = await client.create_customer("Jane", "Smith", "456 Oak Ave")
    account = await server.create_account("Smith,Jane", AccountType.SAVINGS)
    
    # Make various transactions
    await server.deposit(account.account_id, Decimal('1000.00'))  # +1000
    await server.withdraw(account.account_id, Decimal('150.00'))  # -150
    await server.deposit(account.account_id, Decimal('250.00'))   # +250
    await server.withdraw(account.account_id, Decimal('75.00'))   # -75
    
    # Current balance should be 1025.00
    current_account = server.db.get_account(account.account_id)
    assert current_account.balance == Decimal('1025.00')
    
    # Cross month boundary to generate statement
    server.sim_datetime = datetime(2024, 1, 31, 23, 59, 0)
    await server.advance_time(timedelta(minutes=2))  # Cross to Feb 1
    
    # Verify statement was created
    statements = await server.list_statements(account.account_id)
    assert len(statements) == 1
    
    # Get transactions for verification
    transactions = server.db.get_transactions_for_period(
        account.account_id, 
        date(2024, 1, 1), 
        date(2024, 1, 31)
    )
    
    # Verify transaction totals
    total_credits = sum(t.change for t in transactions if t.change > 0)
    total_debits = sum(abs(t.change) for t in transactions if t.change < 0)
    
    assert total_credits == Decimal('1250.00')  # 1000 + 250
    assert total_debits == Decimal('225.00')    # 150 + 75
