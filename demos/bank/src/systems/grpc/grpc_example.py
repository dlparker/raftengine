#!/usr/bin/env python
"""
gRPC Banking Example

This demonstrates the gRPC transport layer that uses traditional RPC method calls
instead of serialized commands. Each banking operation has its own RPC method.

To run:
1. In one terminal: python grpc_server.py
2. In another terminal: python grpc_client.py
"""

import asyncio
from decimal import Decimal
from pathlib  import Path
import sys
top_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(top_dir))
from src.base.client import Client
from src.transports.grpc.client import GrpcServerProxy
from src.base.datatypes import AccountType


async def simple_banking_demo():
    """Simple demo of gRPC banking operations"""
    print("=== gRPC Banking Demo ===")
    
    # Connect to gRPC server
    proxy = GrpcServerProxy('localhost:50051')
    client = Client(proxy)
    
    try:
        # Create a customer
        customer = await client.create_customer("Alice", "Smith", "789 Oak St")
        print(f"Created customer: {customer.first_name} {customer.last_name}")
        
        # Create an account
        account = await client.create_account("Smith,Alice", AccountType.CHECKING)
        print(f"Created checking account: {account.account_id}")
        
        # Make a deposit
        balance = await client.deposit(account.account_id, Decimal('500.00'))
        print(f"Deposited $500, new balance: ${balance}")
        
        print("Demo completed successfully!")
        
    finally:
        proxy.close()


if __name__ == "__main__":
    asyncio.run(simple_banking_demo())
