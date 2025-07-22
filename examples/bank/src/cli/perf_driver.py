#!/usr/bin/env python
import asyncio
import random
import time
import traceback
from decimal import Decimal
from faker import Faker
import argparse
from pathlib import Path
import sys
from raftengine.deck.log_control import LogController
# setup LogControl before importing any modules that might initialize it first
LogController.controller = None
log_control = LogController.make_controller()

this_dir = Path(__file__).resolve().parent
for parent in this_dir.parents:
    if parent.name == 'src':
        if parent not in sys.path:
            sys.path.insert(0, str(parent))
            break
else:
    raise ImportError("Could not find 'src' directory in the path hierarchy")
from base.datatypes import AccountType
from base.operations import Teller


async def setup_ops(teller, c_index):

    fake = Faker()

    customer_count = await teller.get_customer_count()
    new = False
    while customer_count < c_index + 1:
        new = True
        first_name = fake.first_name()
        last_name = fake.last_name()
        address = fake.address().replace('\n', ', ')
        customer = await teller.create_customer(first_name, last_name, address)
        await teller.create_account(customer.cust_id, AccountType.CHECKING)
        customer_count = await teller.get_customer_count()
    
async def time_ops(teller, c_index, loops, condition):
    
    timings = list()
    
    async with condition:
        print(f"{c_index} awaiting condition")
        await asyncio.wait_for(condition.wait(), timeout=0.1)
    print(f"{c_index} running")
    try:
        clist = await teller.list_customers(c_index, 1)
        customer = clist[0]
        accounts = await teller.get_accounts(customer.cust_id)
        checking = accounts[0]

        print(f"{c_index} running")
        for loop_num in range(loops):
            if loop_num % 2 == 0:
                amount = Decimal(str(random.randint(100, 2000)))
                start = time.time()
                await teller.deposit(checking.account_id, amount)
                end = time.time()
                timings.append(end - start)
            else:
                start = time.time()
                await teller.withdraw(checking.account_id, amount)
                end = time.time()
                timings.append(end - start)
    except:
        traceback.print_exc()
    return timings

async def run_clients(teller, count, loops=10):
    timings = {}
    condition = asyncio.Condition()

    async def runner(c_index):
        timings[c_index] = await time_ops(teller, c_index, loops, condition)

    for c_index in range(count):
        await setup_ops(teller, c_index)

    for c_index in range(count):
        asyncio.create_task(runner(c_index))

    await asyncio.sleep(0.001)
    async with condition:
        print('doing notify to start clients')
        condition.notify_all()

    print('waiting for results')
    while len(timings) < count:
        await asyncio.sleep(0.001)
        
    from pprint import pprint
    pprint(timings)

async def main():
    db_path = Path("/tmp/test_banking.db")
    if db_path.exists():
        db_path.unlink()
    teller = Teller(db_file=db_path)
    await run_clients(teller, 5, 10)

if __name__=="__main__":
    asyncio.run(main())
    
