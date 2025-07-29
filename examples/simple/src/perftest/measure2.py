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

async def client_looper(c_index, uri, loops, warmup_loops, result_queue, barrier, rpc_client_class):
    client = RaftClient(uri, rpc_client_class)
    collector = Collector(client)
    # do one to make sure the connection is established
    res = await collector.counter_add('a', 0)
    timings = []
    errors = []
    successes = 0
    failures = 0
    try:
        # Warmup phase (not timed)
        for _ in range(warmup_loops):
            try:
                res = await collector.counter_add('a', 0)
                if res != 0:
                    raise Exception(f'incorrect response "{res}" should have been 0')
            except Exception as e:
                errors.append(str(e))  # Still collect errors during warmup, but don't count as failures

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
            "std_latency": stdev(timings) if len(timings) > 1 else 0,
            "errors": errors  # Now includes all errors from timed loops (and optionally warmup if you want to separate)
        }
        result_queue.put(result)
        await client.close()
    except Exception as e:
        print(f"Client {c_index} process failed: {e}")
        result_queue.put({"client_id": c_index, "error": str(e), "successes": 0, "failures": loops, "errors": [str(e)]})

def client_process(c_index, uri, loops, warmup_loops, result_queue, barrier, rpc_client_class):
    return asyncio.run(client_looper(c_index, uri, loops, warmup_loops, result_queue, barrier, rpc_client_class))

async def one_timing_pass(cluster, num_clients, loops, warmup_loops):

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
                args=(i, uri, loops, warmup_loops, result_queue, barrier, cluster.rpc_tools.get_client_class())
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
            "errors": [error for r in results for error in r.get("errors", [])]  # Aggregate all errors
        }
        return summary
    except:
        traceback.print_exc()
        
async def setup_cluster(args):
    cluster = Cluster(transport=args.transport, base_port=args.base_port)
    # Clear server files before attempting to start
    cluster.clear_server_files()  # Assuming this method exists as per your description; it's synchronous
    
    client_0 = cluster.get_client(index=0)
    try:
        pid = await client_0.direct_server_command("getpid")
        print(f"Existing server detected with PID '{pid}'. Treating as setup error.")
        sys.exit(1)  # Panic/exit as per your instructions
    except (TimeoutError, OSError):
        print("No existing servers detected. Starting servers...")
        await cluster.start_servers()
        if args.transport == 'fastapi':
            # starts slow
            await asyncio.sleep(0.25)
        res = await client_0.direct_server_command("take_power")
        print(f"Call to server 0 direct_server_command('take_power') got '{res}' in reply")
    return cluster

async def run_benchmark(cluster, args):
    summary = await one_timing_pass(cluster, args.clients, args.loops, args.warmup)
    
    # Print summary
    print(f"\nResults for {args.clients} clients:")
    print(f"  Total Requests: {summary['total_requests']}")
    print(f"  Success Rate: {summary['success_rate']:.2%}")
    print(f"  Average Latency: {summary['avg_latency_ms']:.2f} ms")
    print(f"  Latency Std Dev: {summary['std_latency_ms']:.2f} ms")
    print(f"  Total Duration: {summary['total_duration_s']:.2f} s")
    print(f"  Throughput: {summary['throughput_per_second']:.2f} per second")
    if summary["errors"]:
        print(f"  Errors: {summary['errors']}")
    
    if args.json_output:
        export_data = {
            "test_type": "client_scaling",
            "client_range": {"min": args.clients, "max": args.clients},  # Will be updated when merging
            "results": [summary]
        }
        # If file exists, load and append/update
        if Path(args.json_output).exists():
            with open(args.json_output, 'r') as f:
                existing_data = json.load(f)
            existing_data["results"].append(summary)
            # Sort results by total_clients
            existing_data["results"] = sorted(existing_data["results"], key=lambda x: x["total_clients"])
            # Update client_range
            mins = min(r["total_clients"] for r in existing_data["results"])
            maxs = max(r["total_clients"] for r in existing_data["results"])
            existing_data["client_range"] = {"min": mins, "max": maxs}
            export_data = existing_data
        
        with open(args.json_output, 'w') as f:
            json.dump(export_data, f, indent=2)
        print(f"Results appended/updated in {args.json_output}")
    
async def main():
    parser = argparse.ArgumentParser(description='Raft Cluster Performance Testing Tool')
    
    parser.add_argument("--clients", type=int, required=True, help="Number of client processes")
    parser.add_argument("-l", "--loops", type=int, default=1, help="Number of loops for each client")
    parser.add_argument("--warmup", type=int, default=10, help="Number of warmup loops per client (default: 10)")
    parser.add_argument("--json-output", type=str, help="Export results to JSON file (appends if exists)")
    parser.add_argument('--transport', '-t', 
                        choices=['astream', 'aiozmq', 'fastapi',],
                        default='aiozmq',
                        help='Transport mechanism to use')
    parser.add_argument('-b', '--base_port', type=int, default=55555,
                        help='Port number for first node in cluster')
    
    args = parser.parse_args()
    
    cluster = await setup_cluster(args)
    try:
        await run_benchmark(cluster, args)
    except:
        traceback.print_exc()
    finally:
        await cluster.stop_servers()
        if args.transport == 'fastapi':
            # give it time to process client session closes
            await asyncio.sleep(0.25)
    
    
if __name__=="__main__":
    asyncio.run(main())
    
