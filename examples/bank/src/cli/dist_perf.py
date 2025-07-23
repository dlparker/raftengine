#!/usr/bin/env python
import asyncio
import multiprocessing as mp
import random
import time
import traceback
from decimal import Decimal
from faker import Faker
import argparse
from pathlib import Path
import sys
import logging
from statistics import mean, stdev
from typing import Dict, List

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Setup path to import Teller and related modules
this_dir = Path(__file__).resolve().parent
for parent in this_dir.parents:
    if parent.name == 'src':
        if parent not in sys.path:
            sys.path.insert(0, str(parent))
        break
else:
    raise ImportError("Could not find 'src' directory in the path hierarchy")

from raftengine.deck.log_control import LogController
# Initialize LogController
LogController.controller = None
log_control = LogController.make_controller()

from raft_ops.raft_client import RaftClient
from base.collector import Collector
from base.datatypes import AccountType
from base.operations import Teller

async def setup_ops(teller: Teller, c_index: int) -> None:
    """Set up a customer and account for the client."""
    fake = Faker()
    customer_count = await teller.get_customer_count()
    if customer_count < c_index + 1:
        first_name = fake.first_name()
        last_name = fake.last_name()
        address = fake.address().replace('\n', ', ')
        customer = await teller.create_customer(first_name, last_name, address)
        await teller.create_account(customer.cust_id, AccountType.CHECKING)

async def time_ops(c_index: int, uri:str, RPCHelper, loops: int, prep_only) -> Dict:
    """Run deposit/withdrawal operations and collect timings."""
    try:
        logging.info(f"Client {c_index} running setup")
        rch = RPCHelper()
        rpc_client = await rch.rpc_client_maker(uri)
        command_client = RaftClient(rpc_client, rch.rpc_client_maker)
        collector = Collector(command_client)
        
        await setup_ops(collector, c_index)
        if prep_only:
            return {
                "client_id": c_index,
                "successes": 1,
                "failures": 0,
                "latencies": [],
                "avg_latency": 0,
                "std_latency": 0
            }
        
        timings = []
        successes = 0
        failures = 0
        
        clist = await collector.list_customers(c_index, 1)
        if not clist:
            raise ValueError(f"Client {c_index}: No customer found")
        customer = clist[0]
        accounts = await collector.get_accounts(customer.cust_id)
        if not accounts:
            raise ValueError(f"Client {c_index}: No accounts found")
        checking = accounts[0]

        logging.info(f"Client {c_index} running {loops} operations")
        for loop_num in range(loops):
            amount = Decimal(str(random.randint(100, 2000)))
            try:
                start = time.time()
                if loop_num % 2 == 0:
                    await collector.deposit(checking.account_id, amount)
                else:
                    await collector.withdraw(checking.account_id, amount)
                end = time.time()
                timings.append(end - start)
                successes += 1
            except Exception as e:
                logging.error(f"Client {c_index} operation failed: {e}")
                failures += 1
        
        return {
            "client_id": c_index,
            "successes": successes,
            "failures": failures,
            "latencies": timings,
            "avg_latency": mean(timings) if timings else 0,
            "std_latency": stdev(timings) if len(timings) > 1 else 0
        }
    except Exception as e:
        logging.error(f"Client {c_index} failed: {e}")
        return {"client_id": c_index, "error": str(e), "successes": 0, "failures": loops}

def client_process(c_index: int, RPCHelper, uri, loops: int, result_queue: mp.Queue,
                   barrier: mp.Barrier, prep_only=False) -> None:
    """Run a client in a separate process, using asyncio for Teller operations."""
    logging.info(f"Client {c_index} process started")
    try:

        # Wait for all clients to be ready
        barrier.wait()
        
        # Run async operations
        result = asyncio.run(time_ops(c_index, uri, RPCHelper, loops, prep_only))
        result_queue.put(result)
    except Exception as e:
        logging.error(f"Client {c_index} process failed: {e}")
        result_queue.put({"client_id": c_index, "error": str(e), "successes": 0, "failures": loops})

def run_test_harness(uri, RPCHelper, num_clients: int, loops: int, prep_only=False) -> Dict:
    """Run performance test with multiple client processes."""
    # Initialize multiprocessing components
    manager = mp.Manager()
    result_queue = manager.Queue()
    barrier = mp.Barrier(num_clients)
    
    # Create processes for each client
    processes = []
    for i in range(num_clients):
        p = mp.Process(
            target=client_process,
            args=(i, RPCHelper, uri, loops, result_queue, barrier, prep_only)
        )
        processes.append(p)
    
    # Start all processes
    start_time = time.time()
    for p in processes:
        p.start()
    
    # Wait for all processes to complete
    for p in processes:
        p.join()
    
    # Collect results
    results = []
    while not result_queue.empty():
        results.append(result_queue.get())
    
    # Analyze results
    total_successes = sum(r.get("successes", 0) for r in results)
    total_failures = sum(r.get("failures", 0) for r in results)
    avg_latencies = [r["avg_latency"] for r in results if "avg_latency" in r]
    total_duration = time.time() - start_time
    
    summary = {
        "total_clients": num_clients,
        "total_requests": total_successes + total_failures,
        "success_rate": total_successes / (total_successes + total_failures) if total_successes + total_failures > 0 else 0,
        "avg_latency_ms": (mean(avg_latencies) * 1000) if avg_latencies else 0,
        "std_latency_ms": (stdev(avg_latencies) * 1000) if len(avg_latencies) > 1 else 0,
        "total_duration_s": total_duration,
        "errors": [r["error"] for r in results if "error" in r]
    }
    
    return summary

def main():
    parser = argparse.ArgumentParser(description="Performance test harness")
    parser.add_argument("--clients", type=int, default=5, help="Number of client processes")
    parser.add_argument('--transport', '-t', 
                        choices=['astream', 'aiozmq', 'fastapi', 'grpc'],
                        required=True,
                        help='Transport mechanism to use')
    parser.add_argument("--loops", type=int, default=1, help="Number of loops for each client")
    parser.add_argument("--prep_only", action="store_true", help="Set up the conditions, but don't run test")
    args = parser.parse_args()

    transport_offsets = {
        'astream': 0,
        'aiozmq': 100,
        'fastapi': 200,
        'grpc': 300
    }
    port = 50050 + transport_offsets[args.transport]
    # Run the test harness
    host = "localhost"
    if args.transport == 'aiozmq':
        from tx_aiozmq.rpc_helper import RPCHelper
        uri = f"aiozmq://localhost:{port}"
    elif args.transport == 'grpc':
        from tx_grpc.rpc_helper import RPCHelper
        uri = f"grpc://localhost:{port}"
    elif args.transport == 'fastapi':
        from tx_fastapi.rpc_helper import RPCHelper
        uri = f"fastapi://localhost:{port}"
    elif args.transport == 'astream':
        from tx_astream.rpc_helper import RPCHelper
        uri = f"astream://localhost:{port}"
    else:
        raise ValueError(f"Unsupported transport: {args.transport}")
    summary = run_test_harness(uri, RPCHelper, args.clients, args.loops, args.prep_only)
    
    # Print summary
    print("\nTest Summary:")
    print(f"Total Clients: {summary['total_clients']}")
    print(f"Total Requests: {summary['total_requests']}")
    print(f"Success Rate: {summary['success_rate']:.2%}")
    print(f"Average Latency: {summary['avg_latency_ms']:.2f} ms")
    print(f"Latency Std Dev: {summary['std_latency_ms']:.2f} ms")
    print(f"Total Duration: {summary['total_duration_s']:.2f} s")
    throughput = summary['total_requests'] / float(summary['total_duration_s'])
    print(f"Throughput : {throughput:.2f} per second")
    if summary["errors"]:
        print("Errors:", summary["errors"])

if __name__ == "__main__":
    main()
