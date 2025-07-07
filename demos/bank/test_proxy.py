#!/usr/bin/env python
import asyncio
from decimal import Decimal
from src.base.server import Server
from src.transports.indirect.proxy import ServerProxy, ServerWrapper
from src.base.client import Client
from src.base.datatypes import AccountType


async def test_proxy_methods():
    """Test all proxy methods work correctly"""
    server = Server()
    wrapper = ServerWrapper(server)
    proxy = ServerProxy(wrapper)
    client = Client(proxy)
    
    # Test create_customer through full chain
    customer = await client.create_customer("John", "Doe", "123 Main St")
    print(f"Created customer: {customer}")
    
    # Test create_account through proxy
    account = await proxy.create_account("Doe,John", AccountType.CHECKING)
    print(f"Created account: {account}")
    
    # Test deposit through proxy
    balance = await proxy.deposit(account.account_id, Decimal('100.00'))
    print(f"Balance after deposit: {balance}")
    
    # Test withdraw through proxy
    balance = await proxy.withdraw(account.account_id, Decimal('25.00'))
    print(f"Balance after withdrawal: {balance}")
    
    # Test list_accounts through proxy
    accounts = await proxy.list_accounts()
    print(f"All accounts: {len(accounts)} accounts")
    
    # Test get_accounts through proxy
    customer_accounts = await proxy.get_accounts("Doe,John")
    print(f"Customer accounts: {customer_accounts}")
    
    # Test list_statements through proxy
    statements = await proxy.list_statements(account.account_id)
    print(f"Statements: {statements}")
    
    # Test cash_check through proxy
    balance = await proxy.cash_check(account.account_id, Decimal('10.00'))
    print(f"Balance after cash check: {balance}")
    
    # Create second account for transfer test
    account2 = await proxy.create_account("Doe,John", AccountType.SAVINGS)
    result = await proxy.transfer(account.account_id, account2.account_id, Decimal('30.00'))
    print(f"Transfer result: {result}")


if __name__ == "__main__":
    asyncio.run(test_proxy_methods())