#!/usr/bin/env python
"""Banking workflow test helper for integration tests"""
from decimal import Decimal
from datetime import timedelta
from base.datatypes import AccountType


async def validate_banking_workflow(client):
    """Validate all banking operations through any client interface with assertions"""
    
    # Test create_customer
    customer = await client.create_customer("Jane", "Doe", "456 Elm Street")
    assert customer.first_name == "Jane"
    assert customer.last_name == "Doe"
    assert customer.address == "456 Elm Street"
    assert customer.cust_id == 0  # First customer
    
    # Test create_account
    checking = await client.create_account("Doe,Jane", AccountType.CHECKING)
    savings = await client.create_account("Doe,Jane", AccountType.SAVINGS)
    assert checking.account_type == AccountType.CHECKING
    assert savings.account_type == AccountType.SAVINGS
    assert checking.balance == Decimal('0.00')
    assert savings.balance == Decimal('0.00')
    assert checking.customer_id == "Doe,Jane"
    assert savings.customer_id == "Doe,Jane"
    
    # Test deposit
    balance = await client.deposit(checking.account_id, Decimal('1000.00'))
    assert balance == Decimal('1000.00')
    
    balance = await client.deposit(savings.account_id, Decimal('500.00'))
    assert balance == Decimal('500.00')
    
    # Test withdraw
    balance = await client.withdraw(checking.account_id, Decimal('100.00'))
    assert balance == Decimal('900.00')
    
    # Test transfer
    result = await client.transfer(checking.account_id, savings.account_id, Decimal('200.00'))
    assert result is not None
    assert result['from_balance'] == Decimal('700.00')
    assert result['to_balance'] == Decimal('700.00')
    
    # Test cash_check
    balance = await client.cash_check(checking.account_id, Decimal('50.00'))
    assert balance == Decimal('650.00')
    
    # Test list_accounts
    accounts = await client.list_accounts()
    assert len(accounts) == 2
    
    # Find checking and savings accounts
    checking_account = next(acc for acc in accounts if acc.account_id == checking.account_id)
    savings_account = next(acc for acc in accounts if acc.account_id == savings.account_id)
    
    assert checking_account.balance == Decimal('650.00')
    assert savings_account.balance == Decimal('700.00')
    
    # Test get_accounts
    customer_accounts = await client.get_accounts("Doe,Jane")
    assert len(customer_accounts) == 2
    assert checking.account_id in customer_accounts
    assert savings.account_id in customer_accounts
    
    # Test list_statements
    statements = await client.list_statements(checking.account_id)

    assert isinstance(statements, list)
    # Should be empty initially (no monthly statements generated yet)
    
    # Test advance_time
    await client.advance_time(timedelta(hours=24))
    # Should not raise exception
    
    # Verify accounts still exist and have correct balances after time advancement
    accounts_after_time = await client.list_accounts()
    assert len(accounts_after_time) == 2
    
    checking_after = next(acc for acc in accounts_after_time if acc.account_id == checking.account_id)
    savings_after = next(acc for acc in accounts_after_time if acc.account_id == savings.account_id)
    
    assert checking_after.balance == Decimal('650.00')
    assert savings_after.balance == Decimal('700.00')
