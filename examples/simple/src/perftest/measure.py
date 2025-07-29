#!/usr/bin/env python
import asyncio
import argparse
from pathlib import Path
import sys
import time
import json
from statistics import mean, stdev
import multiprocessing as mp
import traceback
from raftengine.deck.log_control import LogController
log_controller = LogController.make_controller()

src_dir = Path(__file__).parent.parent
sys.path.insert(0, str(src_dir))
from raft.run_tools import Cluster
from split_base.collector import Collector
from raft.raft_client import RaftClient

async def client_looper(c_index, uri, loops, result_queue, barrier):
    client = RaftClient(uri)
    collector = Collector(client)
    # do one to make sure the connection is established
    res = await collector.counter_add('a', 0)
    if res != 0:
        raise Exception(f"counter 'a' should have returned 0, not {res}")
    timings = []
    errors = []
    successes = 0
    failures = 0
    try:
        # Wait for all clients to be ready
        barrier.wait()
        all_start = time.perf_counter()
        for loop in range(loops):
            start = time.perf_counter()
            try:
                res = await collector.counter_add('a', 0)
                if res != 0:
                    raise Exception(f'incorrect response "{res}" should have been 0')
                successes += 1
            except Exception as e:
                errors.append(str(e))
                failures += 1
            end = time.perf_counter()
            duration = end-start
            timings.append(duration)
        all_end = time.perf_counter()
        total_duration = all_end - all_start
        
        result = {
            "client_id": c_index,
            "successes": successes,
            "failures": failures,
            "latencies": timings,
            "avg_latency": mean(timings) if timings else 0,
            "std_latency": stdev(timings) if len(timings) > 1 else 0
        }
        if len(errors) > 0:
            result['first_error'] = errors[0]
        result_queue.put(result)
        await client.close()
    except Exception as e:
        print(f"Client {c_index} process failed: {e}")
        result_queue.put({"client_id": c_index, "error": str(e), "successes": 0, "failures": loops})

def client_process(c_index, uri, loops, result_queue, barrier):
    return asyncio.run(client_looper(c_index, uri, loops, result_queue, barrier))

async def one_timing_pass(cluster, num_clients, loops):

    uri = cluster.node_uris[0]
    try:
        manager = mp.Manager()
        result_queue = manager.Queue()
        barrier = mp.Barrier(num_clients)
        
        # Create processes for each client
        processes = []
        for i in range(num_clients):
            p = mp.Process(
                target=client_process,
                args=(i, uri, loops, result_queue, barrier)
            )
            processes.append(p)
            
        # Start all processes
        start_time = time.time()
        for p in processes:
            p.start()
        print(f'{num_clients} clients started')

        # Wait for all processes to complete
        for p in processes:
            p.join()
    
        print(f'{num_clients} clients done')
        # Collect results
        results = []
        while not result_queue.empty():
            results.append(result_queue.get())

        total_successes = sum(r.get("successes", 0) for r in results)
        total_failures = sum(r.get("failures", 0) for r in results)
        avg_latencies = [r["avg_latency"] for r in results if "avg_latency" in r]
        total_duration = time.time() - start_time
    
        throughput = (total_successes + total_failures) / total_duration if total_duration > 0 else 0
        summary = {
            "total_clients": num_clients,
            "total_requests": total_successes + total_failures,
            "success_rate": total_successes / (total_successes + total_failures) if total_successes + total_failures > 0 else 0,
            "avg_latency_ms": (mean(avg_latencies) * 1000) if avg_latencies else 0,
            "std_latency_ms": (stdev(avg_latencies) * 1000) if len(avg_latencies) > 1 else 0,
            "total_duration_s": total_duration,
            "throughput_per_second": throughput,
            "errors": [r["error"] for r in results if "error" in r]
        }
        return summary
    except:
        traceback.print_exc()
        
    
async def main():
    parser = argparse.ArgumentParser(description='Raft Cluster Performance Testing Tool')
    
    # Client configuration - mutually exclusive groups
    client_group = parser.add_mutually_exclusive_group(required=False)
    client_group.add_argument("--clients", type=int, help="Number of client processes (default: 5)")
    client_group.add_argument("--min-clients", type=int, help="Minimum number of clients for range testing")
    parser.add_argument("--max-clients", type=int, help="Maximum number of clients for range testing (requires --min-clients)")
    parser.add_argument("--step-clients", type=int, help="Increase in client count per step (requires --min-clients and requires --max-clients)", default=1)
    parser.add_argument("-l", "--loops", type=int, default=1, help="Number of loops for each client")
    parser.add_argument("--json-output", type=str, help="Export results to JSON file (incompatible with --prep_only)")
    
    args = parser.parse_args()

    if args.min_clients is not None and args.max_clients is None:
        parser.error("--max-clients is required when --min-clients is specified")
    
    if args.max_clients is not None and args.min_clients is None:
        parser.error("--min-clients is required when --max-clients is specified")
    
    if args.min_clients is not None and args.max_clients is not None:
        if args.min_clients > args.max_clients:
            parser.error("--min-clients cannot be greater than --max-clients")
        if args.min_clients < 1:
            parser.error("--min-clients must be at least 1")
    
    if args.min_clients is not None and args.max_clients is not None:
        client_counts = list(range(args.min_clients, args.max_clients + 1, args.step_clients))
    else:
        client_counts = [args.clients if args.clients is not None else 5]

    
    cluster = Cluster(base_port=55555, clear=True)
    cluster.setup_servers()
    client_0 = cluster.get_client(index=0)
    try:
        pid = await client_0.direct_server_command("getpid")
        pre_started = True
    except TimeoutError:
        pre_started = False
        await cluster.start_servers()
        res = await client_0.direct_server_command("take_power")
        print(f"Call to server 0 direct_server_command('take_power') got '{res}' in reply")
    all_results = []
    try:
        for num_clients in client_counts:
            summary = await one_timing_pass(cluster, num_clients, args.loops)
            # Print summary for this client count
            print(f"\nResults for {num_clients} clients:")
            print(f"  Total Requests: {summary['total_requests']}")
            print(f"  Success Rate: {summary['success_rate']:.2%}")
            print(f"  Average Latency: {summary['avg_latency_ms']:.2f} ms")
            print(f"  Latency Std Dev: {summary['std_latency_ms']:.2f} ms")
            print(f"  Total Duration: {summary['total_duration_s']:.2f} s")
            print(f"  Throughput: {summary['throughput_per_second']:.2f} per second")
            if summary["errors"]:
                print(f"  Errors: {summary['errors']}")
            all_results.append(summary)
            
        if args.json_output:
            if len(client_counts) > 1:
                # Multiple runs - export as array
                export_data = {
                    "test_type": "client_scaling",
                    "client_range": {"min": min(client_counts), "max": max(client_counts)},
                    "results": all_results
                }
            else:
                # Single run - export as single object
                export_data = all_results[0]
            with open(args.json_output, 'w') as f:
                json.dump(export_data, f, indent=2)
            print(f"Results exported to {args.json_output}")
    except:
        traceback.print_exc()
    if not pre_started:
        await cluster.stop_servers()
    
    
if __name__=="__main__":
    asyncio.run(main())
