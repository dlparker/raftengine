#!/usr/bin/env python
"""Common banking test functions used across all """
import asyncio
import json
import random
import time
import statistics
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from faker import Faker
from base.datatypes import Customer, Account, AccountType, CommandType


class TimingData:
    """Class to collect and analyze timing data"""
    
    def __init__(self):
        self.timings = defaultdict(list)  # operation_name -> list of times
        self.loop_times = []  # overall loop execution times
        
    def add_timing(self, operation: str, duration: float):
        """Add a timing measurement for an operation"""
        self.timings[operation].append(duration)
        
    def add_loop_timing(self, duration: float):
        """Add a timing measurement for a complete loop"""
        self.loop_times.append(duration)
        
    def get_stats(self, operation: str) -> dict:
        """Get statistics for a specific operation"""
        times = self.timings[operation]
        if not times:
            return {}
            
        return {
            'count': len(times),
            'min': min(times),
            'max': max(times),
            'mean': statistics.mean(times),
            'median': statistics.median(times),
            'stdev': statistics.stdev(times) if len(times) > 1 else 0.0,
            'total': sum(times)
        }
        
    def get_all_stats(self) -> dict:
        """Get statistics for all operations"""
        stats = {}
        for operation in self.timings:
            stats[operation] = self.get_stats(operation)
        if self.loop_times:
            stats['loop_total'] = {
                'count': len(self.loop_times),
                'min': min(self.loop_times),
                'max': max(self.loop_times),
                'mean': statistics.mean(self.loop_times),
                'median': statistics.median(self.loop_times),
                'stdev': statistics.stdev(self.loop_times) if len(self.loop_times) > 1 else 0.0,
                'total': sum(self.loop_times)
            }
        return stats
        
    def print_report(self):
        """Print a formatted timing report"""
        stats = self.get_all_stats()
        
        print("\n" + "="*60)
        print("TIMING REPORT")
        print("="*60)
        
        # Sort operations by total time (descending)
        operations = [(op, data) for op, data in stats.items() if op != 'loop_total']
        operations.sort(key=lambda x: x[1]['total'], reverse=True)
        
        for operation, data in operations:
            print(f"\n{operation.upper()}:")
            print(f"  Count: {data['count']}")
            print(f"  Total: {data['total']:.6f}s")
            print(f"  Mean:  {data['mean']:.6f}s")
            print(f"  Min:   {data['min']:.6f}s")
            print(f"  Max:   {data['max']:.6f}s")
            print(f"  StdDev: {data['stdev']:.6f}s")
            
        if 'loop_total' in stats:
            data = stats['loop_total']
            print(f"\nLOOP TOTAL:")
            print(f"  Count: {data['count']}")
            print(f"  Total: {data['total']:.6f}s")
            print(f"  Mean:  {data['mean']:.6f}s")
            print(f"  Min:   {data['min']:.6f}s")
            print(f"  Max:   {data['max']:.6f}s")
            print(f"  StdDev: {data['stdev']:.6f}s")
            
        print("\n" + "="*60)
        
    def export_to_json(self, file_path: str, metadata: dict = None):
        """Export timing statistics to JSON file
        
        Args:
            file_path: Path to output JSON file
            metadata: Additional metadata to include in export
        """
        stats = self.get_all_stats()
        
        # Prepare export data
        export_data = {
            'timestamp': datetime.now().isoformat(),
            'metadata': metadata or {},
            'statistics': stats,
            'raw_timings': {
                'operations': dict(self.timings),
                'loop_times': self.loop_times
            }
        }
        
        # Write to file
        with open(file_path, 'w') as f:
            json.dump(export_data, f, indent=2)
        
        print(f"\n📊 Timing statistics exported to: {file_path}")


async def validate_teller(teller, loops=1, print_timing=True, json_output=None, metadata=None):
    """Test all banking operations through any teller interface
    
    Args:
        teller: The teller interface to test
        loops: Number of test iterations to run (default: 1)
        print_timing: Whether to print timing report (default: True)
        json_output: Path to JSON file for exporting statistics (default: None)
        metadata: Additional metadata to include in JSON export (default: None)
    """
    
    fake = Faker()
    timing_data = TimingData()

    last_accounts = await teller.list_accounts(-1,1)
    # the database works and the tests too
    if len(last_accounts) == 0:
        starting_account_pos = 0
    else:
        # we can get the number of accounts from the id value, with the way
        starting_account_pos = last_accounts[0].account_id - 1
    
    last_customers = await teller.list_customers(-1,1)
    # the database works and the tests too
    if len(last_customers) == 0:
        starting_customer_pos = 0
    else:
        # we can get the number of customers from the id value, with the way
        starting_customer_pos = last_customers[0].customer_id - 1
    
    for loop_num in range(loops):
        loop_start = time.time()
        await run_single_test(teller, fake, loop_num, timing_data, starting_account_pos, starting_customer_pos)
        loop_end = time.time()
        timing_data.add_loop_timing(loop_end - loop_start)
        
        
    if print_timing:
        timing_data.print_report()
        
    if json_output:
        timing_data.export_to_json(json_output, metadata)
        
    return timing_data


async def run_single_test(teller, fake, loop_num, timing_data, starting_account_pos, starting_customer_pos):
    """Run a single test iteration with randomized data"""
    
    async def timed_operation(operation_name: str, coro):
        """Time an async operation"""
        start = time.time()
        result = await coro
        end = time.time()
        timing_data.add_timing(operation_name, end - start)
        return result
    
    try:
        # Generate random customer data
        first_name = fake.first_name()
        last_name = fake.last_name()
        address = fake.address().replace('\n', ', ')
        
        # Test create_customer
        cust = Customer(first_name, last_name, address)
        customer = await timed_operation('create_customer', 
                                       teller.create_customer(cust.first_name, cust.last_name, cust.address))
        assert customer.first_name == cust.first_name
        assert customer.last_name == cust.last_name
        assert customer.address == cust.address
        assert customer.cust_id is not None

        pos = starting_customer_pos + loop_num
        customers = await timed_operation('list_customers', teller.list_customers(pos, 100))
        assert len(customers) == 1

        sav = Account(AccountType.SAVINGS, customer.cust_id, Decimal('0.00'))
        chk = Account(AccountType.CHECKING, customer.cust_id, Decimal('0.00'))
        # Test create_account
        checking = await timed_operation('create_account', 
                                       teller.create_account(customer.cust_id, AccountType.CHECKING))
        assert checking.account_id is not None
        assert checking.customer_id == chk.customer_id
        assert checking.balance == chk.balance
        savings = await timed_operation('create_account', 
                                      teller.create_account(customer.cust_id, AccountType.SAVINGS))
        assert savings.account_id is not None
        assert savings.customer_id == sav.customer_id
        assert savings.balance == sav.balance
        
        pos = starting_account_pos + (loop_num * 2)
        accounts = await timed_operation('list_accounts', teller.list_accounts(pos, 100))
        assert len(accounts) == 2

        # Test deposit with random amounts
        check_deposit = Decimal(str(random.randint(100, 2000)))
        sav_deposit = Decimal(str(random.randint(50, 1000)))
        
        balance = await timed_operation('deposit', 
                                      teller.deposit(checking.account_id, check_deposit))
        assert balance == check_deposit
        
        balance = await timed_operation('deposit', 
                                      teller.deposit(savings.account_id, sav_deposit))
        assert balance == sav_deposit
        
        # Test withdraw with random amount
        withdraw_amount = Decimal(str(random.randint(10, int(check_deposit) // 2)))
        balance = await timed_operation('withdraw', 
                                      teller.withdraw(checking.account_id, withdraw_amount))
        expected_balance = check_deposit - withdraw_amount
        assert balance == expected_balance
        
        # Test transfer with random amount
        transfer_amount = Decimal(str(random.randint(10, int(expected_balance) // 2)))
        result = await timed_operation('transfer', 
                                     teller.transfer(checking.account_id, savings.account_id, transfer_amount))
        assert result is not None
        expected_check_balance = expected_balance - transfer_amount
        expected_sav_balance = sav_deposit + transfer_amount
        assert result['from_balance'] == expected_check_balance
        assert result['to_balance'] == expected_sav_balance
        
        # Test cash_check with random amount
        cash_amount = Decimal(str(random.randint(5, int(expected_check_balance) // 2)))
        balance = await timed_operation('cash_check', 
                                      teller.cash_check(checking.account_id, cash_amount))
        expected_final_balance = expected_check_balance - cash_amount
        assert balance == expected_final_balance
        
        # list_accounts test moved to separate function after all loops
        
        # Test get_accounts
        customer_accounts = await timed_operation('get_accounts', 
                                                teller.get_accounts(customer.cust_id))
        assert len(customer_accounts) == 2
        assert checking.account_id in customer_accounts
        assert savings.account_id in customer_accounts
        
        # Test list_statements
        statements = await timed_operation('list_statements', 
                                         teller.list_statements(checking.account_id))
        assert isinstance(statements, list)
        # Statements may exist from previous loops, so just verify it's a list
        
        # Test advance_time with random duration
        hours = random.randint(1, 72)
        await timed_operation('advance_time', 
                            teller.advance_time(timedelta(hours=hours)))
        # No return value to assert, just ensure it doesn't raise an exception
        
    except Exception as e:
        print(f"✗ Error in loop {loop_num}: {e}")
        raise


    
    
    
    
    
    
