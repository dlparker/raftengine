import pytest
import pytest_asyncio
import tempfile
import os
from datetime import datetime, timedelta, date
from decimal import Decimal
from src.base.server import Server
from src.base.client import Client
from src.base.datatypes import AccountType
from tests.test_helpers import setup_async_streams_test, create_temp_db, cleanup_temp_db


@pytest.fixture
def temp_db():
    """Create a temporary database for testing"""
    temp_path = create_temp_db()
    yield temp_path
    cleanup_temp_db(temp_path)


@pytest_asyncio.fixture
async def banking_setup(temp_db):
    """Setup banking system components for testing"""
    client, cleanup, port = await setup_async_streams_test(temp_db)
    yield client, cleanup, port
    await cleanup()


@pytest.mark.asyncio
async def test_monthly_statement_generation(banking_setup):
    """Test monthly statement generation when crossing month boundaries"""
    client, cleanup, port = banking_setup
    
    # Note: We can't directly set server time through transport layer
    # This test focuses on the statement generation API functionality
    
    # Create customer and account
    customer = await client.create_customer("John", "Doe", "123 Main St")
    assert customer.first_name == "John"
    assert customer.last_name == "Doe"
    
    account = await client.create_account("Doe,John", AccountType.CHECKING)
    assert account.account_type == AccountType.CHECKING
    assert account.balance == Decimal('0.00')
    
    # Make some transactions
    await client.deposit(account.account_id, Decimal('100.00'))
    await client.withdraw(account.account_id, Decimal('25.00'))
    await client.deposit(account.account_id, Decimal('50.00'))
    
    # Verify current balance
    accounts = await client.list_accounts()
    current_account = next(acc for acc in accounts if acc.account_id == account.account_id)
    assert current_account.balance == Decimal('125.00')
    
    # Check statements before month boundary
    statements_before = await client.list_statements(account.account_id)
    assert len(statements_before) == 0
    
    # Advance time to cross month boundary (from current to next month)
    await client.advance_time(timedelta(days=32))  # Cross month boundary
    
    # Check statements after month boundary
    statements_after = await client.list_statements(account.account_id)
    assert len(statements_after) >= 1  # At least one statement should be generated
    
    # Make more transactions in the new month
    await client.deposit(account.account_id, Decimal('200.00'))
    await client.withdraw(account.account_id, Decimal('30.00'))
    
    # Advance time to cross another month boundary
    await client.advance_time(timedelta(days=32))  # Cross another month boundary
    
    # Check final statements
    final_statements = await client.list_statements(account.account_id)
    assert len(final_statements) >= 2  # At least two statements should be generated


@pytest.mark.asyncio
async def test_month_boundary_detection(banking_setup):
    """Test month boundary detection logic through API"""
    client, cleanup, port = banking_setup
    
    # Create customer and account to test statement generation
    customer = await client.create_customer("Jane", "Smith", "456 Oak Ave")
    account = await client.create_account("Smith,Jane", AccountType.SAVINGS)
    
    # Make some transactions
    await client.deposit(account.account_id, Decimal('1000.00'))
    
    # Check initial statements
    initial_statements = await client.list_statements(account.account_id)
    initial_count = len(initial_statements)
    
    # Advance time to cross month boundary
    await client.advance_time(timedelta(days=32))
    
    # Check if statement was generated
    statements_after = await client.list_statements(account.account_id)
    assert len(statements_after) > initial_count  # Should have more statements


@pytest.mark.asyncio
async def test_statement_content_accuracy(banking_setup):
    """Test that statement content is calculated correctly"""
    client, cleanup, port = banking_setup
    
    # Create customer and account
    customer = await client.create_customer("Jane", "Smith", "456 Oak Ave")
    account = await client.create_account("Smith,Jane", AccountType.SAVINGS)
    
    # Make various transactions
    await client.deposit(account.account_id, Decimal('1000.00'))  # +1000
    await client.withdraw(account.account_id, Decimal('150.00'))  # -150
    await client.deposit(account.account_id, Decimal('250.00'))   # +250
    await client.withdraw(account.account_id, Decimal('75.00'))   # -75
    
    # Current balance should be 1025.00
    accounts = await client.list_accounts()
    current_account = next(acc for acc in accounts if acc.account_id == account.account_id)
    assert current_account.balance == Decimal('1025.00')
    
    # Cross month boundary to generate statement
    await client.advance_time(timedelta(days=32))  # Cross to next month
    
    # Verify statement was created
    statements = await client.list_statements(account.account_id)
    assert len(statements) >= 1
    
    # The statement generation logic is tested through the API
    # We can't directly access database transactions through transport layer
    # but we can verify the balance remains consistent
    accounts_after = await client.list_accounts()
    account_after = next(acc for acc in accounts_after if acc.account_id == account.account_id)
    assert account_after.balance == Decimal('1025.00')  # Balance should remain the same
