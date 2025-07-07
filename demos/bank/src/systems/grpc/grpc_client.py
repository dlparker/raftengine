#!/usr/bin/env python
"""gRPC Banking Client Test"""
import argparse
import asyncio
from decimal import Decimal
from datetime import timedelta
from pathlib  import Path
import sys
top_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(top_dir))
from src.base.client import Client
from src.transports.grpc.client import GrpcServerProxy
from src.base.datatypes import AccountType


async def test_grpc_banking(server_address):
    """Test all banking operations through gRPC"""
    print(f"=== gRPC Banking Client ===")
    print(f"Connecting to: {server_address}")
    
    # Create gRPC proxy and client
    proxy = GrpcServerProxy(server_address)
    client = Client(proxy)
    
    try:
        # Test create_customer
        print("\n1. Creating customer...")
        customer = await client.create_customer("Jane", "Doe", "456 Elm Street")
        print(f"   ✓ Created: {customer.first_name} {customer.last_name} (ID: {customer.cust_id})")
        
        # Test create_account
        print("\n2. Creating accounts...")
        checking = await client.create_account("Doe,Jane", AccountType.CHECKING)
        savings = await client.create_account("Doe,Jane", AccountType.SAVINGS)
        print(f"   ✓ Checking account: {checking.account_id}")
        print(f"   ✓ Savings account: {savings.account_id}")
        
        # Test deposit
        print("\n3. Making deposits...")
        balance = await client.deposit(checking.account_id, Decimal('1000.00'))
        print(f"   ✓ Deposited $1000 to checking, balance: ${balance}")
        
        balance = await client.deposit(savings.account_id, Decimal('500.00'))
        print(f"   ✓ Deposited $500 to savings, balance: ${balance}")
        
        # Test withdraw
        print("\n4. Making withdrawal...")
        balance = await client.withdraw(checking.account_id, Decimal('100.00'))
        print(f"   ✓ Withdrew $100 from checking, balance: ${balance}")
        
        # Test transfer
        print("\n5. Making transfer...")
        result = await client.transfer(checking.account_id, savings.account_id, Decimal('200.00'))
        print(f"   ✓ Transferred $200: Checking=${result['from_balance']}, Savings=${result['to_balance']}")
        
        # Test cash_check
        print("\n6. Cashing check...")
        balance = await client.cash_check(checking.account_id, Decimal('50.00'))
        print(f"   ✓ Cashed $50 check, balance: ${balance}")
        
        # Test list_accounts
        print("\n7. Listing all accounts...")
        accounts = await client.list_accounts()
        print(f"   ✓ Total accounts: {len(accounts)}")
        for account in accounts:
            print(f"     - Account {account.account_id}: {account.account_type.value}, ${account.balance}")
        
        # Test get_accounts
        print("\n8. Getting customer accounts...")
        customer_accounts = await client.get_accounts("Doe,Jane")
        print(f"   ✓ Jane's accounts: {customer_accounts}")
        
        # Test list_statements
        print("\n9. Listing statements...")
        statements = await client.list_statements(checking.account_id)
        print(f"   ✓ Statements for account {checking.account_id}: {len(statements)} statements")
        
        # Test advance_time
        print("\n10. Advancing time...")
        await client.advance_time(timedelta(hours=24))
        print("    ✓ Advanced time by 24 hours")
        
        print("\n=== All gRPC operations completed successfully! ===")
        
    except Exception as e:
        print(f"✗ Error: {e}")
        raise
    finally:
        # Clean up
        proxy.close()


async def main():
    parser = argparse.ArgumentParser(description='gRPC Banking Client')
    parser.add_argument('--host', '-H', 
                       default='localhost',
                       help='Server host address (default: localhost)')
    parser.add_argument('--port', '-p', 
                       type=int, default=50051,
                       help='Server port (default: 50051)')
    
    args = parser.parse_args()
    server_address = f"{args.host}:{args.port}"
    
    await test_grpc_banking(server_address)

if __name__ == "__main__":
    asyncio.run(main())
