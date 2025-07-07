#!/usr/bin/env python
import asyncio
from decimal import Decimal
from datetime import timedelta
from src.base.server import Server
from src.no_raft.transports import ServerProxy, ServerWrapper
from src.base.client import Client
from src.base.datatypes import AccountType


async def test_full_chain():
    """Test all methods through the complete Client -> Proxy -> Wrapper -> Server chain"""
    server = Server()
    wrapper = ServerWrapper(server)
    proxy = ServerProxy(wrapper)
    client = Client(proxy)
    
    print("=== Testing Full Banking Chain ===")
    
    # Test create_customer through full chain
    customer = await client.create_customer("Alice", "Johnson", "789 Pine St")
    print(f"✓ Created customer: {customer.first_name} {customer.last_name}")
    
    # Test create_account through full chain
    checking = await client.create_account("Johnson,Alice", AccountType.CHECKING)
    savings = await client.create_account("Johnson,Alice", AccountType.SAVINGS)
    print(f"✓ Created accounts: {checking.account_id} (CHECKING), {savings.account_id} (SAVINGS)")
    
    # Test deposit through full chain
    balance = await client.deposit(checking.account_id, Decimal('500.00'))
    print(f"✓ Deposited $500, balance: ${balance}")
    
    # Test withdraw through full chain
    balance = await client.withdraw(checking.account_id, Decimal('75.50'))
    print(f"✓ Withdrew $75.50, balance: ${balance}")
    
    # Test transfer through full chain
    result = await client.transfer(checking.account_id, savings.account_id, Decimal('200.00'))
    print(f"✓ Transferred $200: Checking=${result['from_balance']}, Savings=${result['to_balance']}")
    
    # Test cash_check through full chain
    balance = await client.cash_check(checking.account_id, Decimal('25.00'))
    print(f"✓ Cashed check $25, balance: ${balance}")
    
    # Test list_accounts through full chain
    accounts = await client.list_accounts()
    print(f"✓ Listed accounts: {len(accounts)} total accounts")
    
    # Test get_accounts through full chain
    customer_accounts = await client.get_accounts("Johnson,Alice")
    print(f"✓ Customer accounts: {customer_accounts}")
    
    # Test list_statements through full chain
    statements = await client.list_statements(checking.account_id)
    print(f"✓ Statements: {len(statements)} statements")
    
    # Test advance_time through full chain
    await client.advance_time(timedelta(hours=2))
    print(f"✓ Advanced time by 2 hours")
    
    print("\n=== All Client Methods Working! ===")


if __name__ == "__main__":
    asyncio.run(test_full_chain())