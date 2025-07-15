#!/usr/bin/env python
"""Common banking test functions used across all """
import asyncio
import random
from decimal import Decimal
from datetime import timedelta
from pathlib import Path
import sys
this_dir = Path(__file__).resolve().parent
for parent in this_dir.parents:
    if parent.name == 'src':
        if parent not in sys.path:
            sys.path.insert(0, str(parent))
            break
else:
    raise ImportError("Could not find 'src' directory in the path hierarchy")

from faker import Faker
from base.datatypes import AccountType


async def demo_teller(teller, use_random_data=False):
    """Test all banking operations through any teller interface
    
    Args:
        teller: The teller interface to test
        use_random_data: If True, use random names/addresses/amounts (default: False)
    """
    
    try:
        if use_random_data:
            fake = Faker()
            first_name = fake.first_name()
            last_name = fake.last_name()
            address = fake.address().replace('\n', ', ')
        else:
            first_name = "Jane"
            last_name = "Doe"
            address = "456 Elm Street"
            
        # Test create_customer
        print("\n1. Creating customer...")
        customer = await teller.create_customer(first_name, last_name, address)
        print(f"   ✓ Created: {customer.first_name} {customer.last_name} (ID: {customer.cust_id})")
        
        # Test create_account
        print("\n2. Creating accounts...")
        checking = await teller.create_account(customer.cust_id, AccountType.CHECKING)
        savings = await teller.create_account(customer.cust_id, AccountType.SAVINGS)
        print(f"   ✓ Checking account: {checking.account_id}")
        print(f"   ✓ Savings account: {savings.account_id}")
        
        # Test deposit
        print("\n3. Making deposits...")
        if use_random_data:
            check_deposit = Decimal(str(random.randint(100, 2000)))
            sav_deposit = Decimal(str(random.randint(50, 1000)))
        else:
            check_deposit = Decimal('1000.00')
            sav_deposit = Decimal('500.00')
            
        balance = await teller.deposit(checking.account_id, check_deposit)
        print(f"   ✓ Deposited ${check_deposit} to checking, balance: ${balance}")
        
        balance = await teller.deposit(savings.account_id, sav_deposit)
        print(f"   ✓ Deposited ${sav_deposit} to savings, balance: ${balance}")
        
        # Test withdraw
        print("\n4. Making withdrawal...")
        if use_random_data:
            withdraw_amount = Decimal(str(random.randint(10, int(check_deposit) // 2)))
        else:
            withdraw_amount = Decimal('100.00')
            
        balance = await teller.withdraw(checking.account_id, withdraw_amount)
        print(f"   ✓ Withdrew ${withdraw_amount} from checking, balance: ${balance}")
        
        # Test transfer
        print("\n5. Making transfer...")
        if use_random_data:
            current_check_balance = check_deposit - withdraw_amount
            transfer_amount = Decimal(str(random.randint(10, int(current_check_balance) // 2)))
        else:
            transfer_amount = Decimal('200.00')
            
        result = await teller.transfer(checking.account_id, savings.account_id, transfer_amount)
        print(f"   ✓ Transferred ${transfer_amount}: Checking=${result['from_balance']}, Savings=${result['to_balance']}")
        
        # Test cash_check
        print("\n6. Cashing check...")
        if use_random_data:
            current_balance = result['from_balance']
            cash_amount = Decimal(str(random.randint(5, int(current_balance) // 2)))
        else:
            cash_amount = Decimal('50.00')
            
        balance = await teller.cash_check(checking.account_id, cash_amount)
        print(f"   ✓ Cashed ${cash_amount} check, balance: ${balance}")
        
        # Test list_accounts
        print("\n7. Listing all accounts...")
        accounts = await teller.list_accounts()
        print(f"   ✓ Total accounts: {len(accounts)}")
        for account in accounts:
            print(f"     - Account {account.account_id}: {account.account_type.value}, ${account.balance}")
        
        # Test get_accounts
        print("\n8. Getting customer accounts...")
        customer_accounts = await teller.get_accounts(customer.cust_id)
        print(f"   ✓ {customer.first_name}'s accounts: {customer_accounts}")
        
        # Test list_statements
        print("\n9. Listing statements...")
        statements = await teller.list_statements(checking.account_id)
        print(f"   ✓ Statements for account {checking.account_id}: {len(statements)} statements")
        
        # Test advance_time
        print("\n10. Advancing time...")
        if use_random_data:
            hours = random.randint(1, 72)
        else:
            hours = 24
            
        await teller.advance_time(timedelta(hours=hours))
        print(f"    ✓ Advanced time by {hours} hours")
        
        print("\n=== All banking operations completed successfully! ===")
        
    except Exception as e:
        print(f"✗ Error: {e}")
        raise


    
    
    
    
    
    
