#!/usr/bin/env python
import asyncio
import argparse
from pathlib import Path
import sys
import time
import json
import subprocess
from statistics import mean, stdev
import multiprocessing as mp
import traceback
from raftengine.deck.log_control import LogController
log_controller = LogController.make_controller()

src_dir = Path(__file__).parent.parent
sys.path.insert(0, str(src_dir))
from split_base.collector import Collector
from raft.raft_client import RaftClient
from rpc.run_tools import RunTools as RPCRunTools

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

async def one_timing_pass(transport, base_port, num_clients, loops, warmup_loops):
    node_uris = get_cluster_node_uris(transport, base_port)
    uri = node_uris[0]
    rpc_tools = RPCRunTools(transport)
    
    try:
        manager = mp.Manager()
        result_queue = manager.Queue()
        barrier = mp.Barrier(num_clients)
        
        # Create processes for each client
        processes = []
        for i in range(num_clients):
            p = mp.Process(
                target=client_process,
                args=(i, uri, loops, warmup_loops, result_queue, barrier, rpc_tools.get_client_class())
            )
            processes.append(p)
            
        # Start all processes
        start_time = time.time()
        for p in processes:
            p.start()
        print(f'{num_clients} clients started')
        
        # Add periodic status reporting
        last_status_time = start_time
        status_interval = 2.0  # Report every 2 seconds
        
        # Wait for all processes to complete with periodic status updates
        all_finished = False
        while not all_finished:
            # Check if all processes are done
            all_finished = all(not p.is_alive() for p in processes)
            
            if not all_finished:
                current_time = time.time()
                if current_time - last_status_time >= status_interval:
                    elapsed = current_time - start_time
                    active_clients = sum(1 for p in processes if p.is_alive())
                    print(f"Status update: {elapsed:.1f}s elapsed, {active_clients}/{num_clients} clients still active")
                    last_status_time = current_time
                
                # Wait a bit before checking again
                await asyncio.sleep(0.1)
        
        # Ensure all processes are joined
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
        
def validate_cluster_ready(transport, base_port):
    """Validate that cluster is running and has elected a leader using cluster_control.py"""
    cluster_control_path = Path(__file__).parent.parent / 'raft' / 'cluster_control.py'
    
    # Check if cluster is running
    try:
        status_result = subprocess.run([
            sys.executable, str(cluster_control_path), 
            'status', '-t', transport, '-b', str(base_port), '-i', '0'
        ], capture_output=True, text=True, timeout=5)
        
        if status_result.returncode != 0:
            print(f"Error: Cluster status check failed: {status_result.stderr}")
            sys.exit(1)
            
    except subprocess.TimeoutExpired:
        print("Error: Cluster status check timed out - cluster likely not running")
        sys.exit(1)
    except Exception as e:
        print(f"Error: Failed to check cluster status: {e}")
        sys.exit(1)
    
    # Check if leader is elected
    try:
        leader_result = subprocess.run([
            sys.executable, str(cluster_control_path),
            'get_leader', '-t', transport, '-b', str(base_port)
        ], capture_output=True, text=True, timeout=5)
        
        if leader_result.returncode != 0 or 'error' in leader_result.stdout.lower():
            print(f"Error: No leader elected or leader check failed: {leader_result.stdout}")
            sys.exit(1)
            
        leader_uri = leader_result.stdout.strip()
        print(f"Cluster validation successful - Leader: {leader_uri}")
        
    except subprocess.TimeoutExpired:
        print("Error: Leader check timed out")
        sys.exit(1)
    except Exception as e:
        print(f"Error: Failed to check cluster leader: {e}")
        sys.exit(1)

def get_cluster_node_uris(transport, base_port):
    """Get cluster node URIs based on transport and base port"""
    node_uris = []
    for port in range(base_port, base_port + 3):
        uri = f"{transport}://127.0.0.1:{port}"
        node_uris.append(uri)
    return node_uris

async def run_benchmark(args):
    summary = await one_timing_pass(args.transport, args.base_port, args.clients, args.loops, args.warmup)
    
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
    parser = argparse.ArgumentParser(description='Raft Cluster Performance Testing Tool - Client Runner')
    
    parser.add_argument("--clients", type=int, required=True, help="Number of client processes")
    parser.add_argument("-l", "--loops", type=int, default=1, help="Number of loops for each client")
    parser.add_argument("--warmup", type=int, default=10, help="Number of warmup loops per client (default: 10)")
    parser.add_argument("--json-output", type=str, help="Export results to JSON file (appends if exists)")
    parser.add_argument('--transport', '-t', 
                        choices=['astream', 'aiozmq', 'fastapi','grpc'],
                        default='aiozmq',
                        help='Transport mechanism to use')
    parser.add_argument('-b', '--base_port', type=int, default=55555,
                        help='Port number for first node in cluster')
    
    args = parser.parse_args()
    
    # Validate cluster is ready before starting tests
    print(f"Validating cluster readiness (transport: {args.transport}, base_port: {args.base_port})...")
    validate_cluster_ready(args.transport, args.base_port)
    
    try:
        await run_benchmark(args)
    except:
        traceback.print_exc()
        sys.exit(1)
    
    
if __name__=="__main__":
    asyncio.run(main())
    
