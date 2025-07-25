#!/usr/bin/env python
"""
Raft Cluster Performance Testing Tool
Combines cluster management from validate_raft.py with client timing from dist_perf.py
"""
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
import json

class ClusterManager:
    """Manages a 3-node Raft cluster lifecycle"""
    
    def __init__(self, transport, base_port=50050, slow_timeouts=True):
        self.transport = transport
        self.base_port = base_port
        self.slow_timeouts = slow_timeouts
        
        # Get cluster nodes and RPC helper using the new method
        self.cluster_nodes, self.RPCHelper = nodes_and_helper(transport, base_port=base_port, node_count=3)
    
    async def start_cluster(self) -> bool:
        """Start all 3 servers in the cluster using subprocess"""
        import subprocess
        import sys
        
        print(f"Starting {self.transport} cluster on base port {self.base_port}")
        print(f"Cluster nodes: {self.cluster_nodes}")
        
        success_count = 0
        
        # Start all servers using subprocess
        for index in range(3):
            print(f"Starting server {index}...")
            success = await self._start_server(index)
            if success:
                success_count += 1
            else:
                print(f"Failed to start server {index}")
        
        if success_count == 3:
            print("All servers started successfully")
            return True
        else:
            print(f"Only {success_count}/3 servers started successfully")
            # Cleanup partially started cluster
            await self.stop_cluster()
            return False
    
    async def _start_server(self, index: int) -> bool:
        """Start a specific server using subprocess"""
        import subprocess
        import sys
        
        try:
            # Use subprocess to start the server like cluster_control.py does
            raft_server_path = Path(Path(__file__).parent, 'raft_server.py')
            cmd = [sys.executable, str(raft_server_path), '--transport', self.transport,
                   '--index', str(index)]
            if self.slow_timeouts:
                cmd.append('--slow_timeouts')
            
            work_dir = Path('/tmp', f"raft_server.{self.transport}.{index}")
            work_dir.mkdir(exist_ok=True)
            stdout_file = Path(work_dir, 'server.stdout')
            stderr_file = Path(work_dir, 'server.stderr')
            
            print(f"Command: {' '.join(cmd)}")
            
            with open(stdout_file, 'w') as stdout_f, open(stderr_file, 'w') as stderr_f:
                process = subprocess.Popen(cmd, stdout=stdout_f, stderr=stderr_f, start_new_session=True)
            
            # Wait a moment to see if process starts successfully
            await asyncio.sleep(0.5)
            if process.poll() is None:  # Process is still running
                print(f"Server {index} started successfully")
                print(f"  stdout: {stdout_file}")
                print(f"  stderr: {stderr_file}")
                return True
            else:
                print(f"Server {index} failed to start")
                # Read the error logs
                if stderr_file.exists():
                    with open(stderr_file, 'r') as f:
                        stderr_content = f.read()
                    if stderr_content:
                        print(f"stderr: {stderr_content}")
                return False
                
        except Exception as e:
            print(f"Error starting server {index}: {e}")
            return False
    
    async def stop_cluster(self) -> bool:
        """Stop all servers in the cluster using LocalCollector"""
        print("Stopping cluster via local_commands...")
        success_count = 0
        
        for index in range(3):
            try:
                node_uri = self.cluster_nodes[index]
                print(f"Stopping server {index} at {node_uri}")
                
                # Try to connect and send stop command via RPC
                try:
                    rpc_client = await self.RPCHelper().rpc_client_maker(node_uri)
                    server_local_commands = LocalCollector(rpc_client)
                    
                    # Get PID first to confirm server is reachable
                    pid = await server_local_commands.get_pid()
                    print(f'Server {index} has PID {pid}')
                    
                    # Send stop command
                    await server_local_commands.stop_server()
                    await rpc_client.close()
                    
                    print(f"Sent stop command to server {index}")
                    success_count += 1
                    
                except Exception as rpc_error:
                    print(f"RPC stop failed for server {index}: {rpc_error}")
                    # Server might already be stopped or unreachable
                    success_count += 1
                    
            except Exception as e:
                print(f"Error stopping server {index}: {e}")
        
        print(f"Sent stop commands to {success_count}/3 servers")
        
        # Wait a moment for servers to shut down
        await asyncio.sleep(1.0)
        
        return success_count == 3
    
    async def get_cluster_status(self) -> dict:
        """Get status of all cluster nodes using LocalCollector"""
        status = {}
        for index in range(3):
            try:
                node_uri = self.cluster_nodes[index]
                rpc_client = await self.RPCHelper().rpc_client_maker(node_uri)
                server_local_commands = LocalCollector(rpc_client)
                
                # Get detailed status from the server
                server_status = await server_local_commands.get_status()
                server_status['running'] = True
                await rpc_client.close()
                
                status[index] = server_status
            except Exception as e:
                status[index] = {'error': str(e), 'running': False}
        return status
    
    async def is_cluster_running(self) -> bool:
        """Check if the cluster is already running by testing connectivity to all nodes"""
        running_count = 0
        for index in range(3):
            try:
                node_uri = self.cluster_nodes[index]
                rpc_client = await self.RPCHelper().rpc_client_maker(node_uri)
                server_local_commands = LocalCollector(rpc_client)
                
                # Try to get PID - if this succeeds, server is running
                await server_local_commands.get_pid()
                await rpc_client.close()
                running_count += 1
            except Exception:
                # Server not reachable, probably not running
                pass
        
        # Consider cluster running if all 3 nodes are reachable
        return running_count == 3
    
    def get_leader_uri(self):
        """Get URI for the leader (node 0)"""
        return self.cluster_nodes[0]

async def setup_ops(teller, c_index: int) -> None:
    """Set up a customer and account for the client."""
    fake = Faker()
    customer_count = await teller.get_customer_count()
    if customer_count < c_index + 1:
        first_name = fake.first_name()
        last_name = fake.last_name()
        address = fake.address().replace('\n', ', ')
        customer = await teller.create_customer(first_name, last_name, address)
        await teller.create_account(customer.cust_id, AccountType.CHECKING)

async def time_ops(c_index: int, uri: str, RPCHelper, loops: int, prep_only) -> dict:
    """Run deposit/withdrawal operations and collect timings."""
    try:
        logging.info(f"Client {c_index} running setup")
        rch = RPCHelper()
        rpc_client = await rch.rpc_client_maker(uri)
        command_client = RaftClient(rpc_client, RPCHelper)
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

def run_test_harness(uri, RPCHelper, num_clients: int, loops: int, prep_only=False) -> dict:
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

async def main():
    parser = argparse.ArgumentParser(
        description='Raft Cluster Performance Testing Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --transport grpc --clients 5 --loops 10
  %(prog)s --transport aiozmq --clients 3 --loops 20 --prep_only
  %(prog)s --transport fastapi --clients 10 --loops 5

Available transports:
  astream, aiozmq, fastapi, grpc
        """)
    
    parser.add_argument('--transport', '-t', 
                        choices=['astream', 'aiozmq', 'fastapi', 'grpc'],
                        required=True,
                        help='Transport mechanism to use')
    parser.add_argument('--base-port', '-b', type=int, default=50050,
                        help='Base port for cluster (default: 50050)')
    parser.add_argument('--cluster-startup-delay', type=float, default=1.0,
                        help='Delay in seconds to wait for cluster formation (default: 1.0)')
    # Client configuration - mutually exclusive groups
    client_group = parser.add_mutually_exclusive_group(required=False)
    client_group.add_argument("--clients", type=int, help="Number of client processes (default: 5)")
    client_group.add_argument("--min-clients", type=int, help="Minimum number of clients for range testing")
    parser.add_argument("--max-clients", type=int, help="Maximum number of clients for range testing (requires --min-clients)")
    parser.add_argument("--loops", type=int, default=1, help="Number of loops for each client")
    parser.add_argument("--prep_only", action="store_true", help="Set up the conditions, but don't run test")
    parser.add_argument("--json-output", type=str, help="Export results to JSON file (incompatible with --prep_only)")
    
    args = parser.parse_args()
    
    # Validate argument combinations
    if args.prep_only and args.json_output:
        parser.error("--json-output cannot be used with --prep_only")
    
    if args.min_clients is not None and args.max_clients is None:
        parser.error("--max-clients is required when --min-clients is specified")
    
    if args.max_clients is not None and args.min_clients is None:
        parser.error("--min-clients is required when --max-clients is specified")
    
    if args.min_clients is not None and args.max_clients is not None:
        if args.min_clients > args.max_clients:
            parser.error("--min-clients cannot be greater than --max-clients")
        if args.min_clients < 1:
            parser.error("--min-clients must be at least 1")
    
    # Determine client counts to test
    if args.min_clients is not None and args.max_clients is not None:
        client_counts = list(range(args.min_clients, args.max_clients + 1))
    else:
        # Use default of 5 if --clients not specified
        client_counts = [args.clients if args.clients is not None else 5]
    
    # Create cluster manager
    cluster = ClusterManager(args.transport, args.base_port, slow_timeouts=True)
    
    # Check if cluster is already running
    cluster_was_running = await cluster.is_cluster_running()
    if cluster_was_running:
        print(f"Cluster is already running on {args.transport} transport (base port {args.base_port})")
        cluster_started = True
    else:
        print(f"Starting {args.transport} cluster...")
        cluster_started = await cluster.start_cluster()
        if not cluster_started:
            print("Failed to start cluster")
            sys.exit(1)
        try:

            # Wait for cluster formation
            print(f"Waiting {args.cluster_startup_delay}s for cluster formation...")
            await asyncio.sleep(args.cluster_startup_delay)

            # Start Raft operations on all servers
            print("Starting Raft operations on all servers...")
            for index in range(3):
                try:
                    node_uri = cluster.cluster_nodes[index]
                    rpc_client = await cluster.RPCHelper().rpc_client_maker(node_uri)
                    server_local_commands = LocalCollector(rpc_client)
                    await server_local_commands.start_raft()
                    await rpc_client.close()
                    print(f"  Started Raft on node {index}")
                except Exception as e:
                    print(f"  Warning: Failed to start Raft on node {index}: {e}")

            # Wait a moment for Raft to initialize
            await asyncio.sleep(0.5)

            # Trigger leader election since we're using slow timeouts
            print("Triggering leader election on node 0...")
            try:
                leader_uri = cluster.cluster_nodes[0]
                rpc_client = await cluster.RPCHelper().rpc_client_maker(leader_uri)
                server_local_commands = LocalCollector(rpc_client)
                await server_local_commands.start_campaign()
                await rpc_client.close()
                print("Election triggered successfully")

                # Wait a moment for election to complete
                await asyncio.sleep(1.0)
            except Exception as e:
                print(f"Warning: Failed to trigger election: {e}")

            # Check cluster status
            print("Checking cluster status...")
            cluster_status = await cluster.get_cluster_status()
            for index, status in cluster_status.items():
                if status.get('running'):
                    role = "Leader" if status.get('is_leader') else "Follower"
                    term = status.get('term', 'unknown')
                    print(f"  Node {index}: {role} (term {term})")
                else:
                    print(f"  Node {index}: Not running - {status.get('error', 'unknown error')}")

        except Exception as e:
            print(f"Error during cluster setup: {traceback.format_exc()}")
            sys.exit(1)
        finally:
            print("Stopping cluster...")
            await cluster.stop_cluster()
    try:
        # Get leader URI (node 0)
        leader_uri = cluster.cluster_nodes[0]
        leader_uri = cluster.get_leader_uri()
        print(f"Running performance tests against leader at {leader_uri}")

        # Run tests for each client count
        all_results = []
        for client_count in client_counts:
            print(f"\n=== Testing with {client_count} clients ===")
            
            # Run the test harness against the leader
            summary = run_test_harness(leader_uri, cluster.RPCHelper, client_count, args.loops, args.prep_only)
            
            # Add setup data to summary for JSON export
            summary.update({
                "setup": {
                    "transport": args.transport,
                    "num_clients": client_count,
                    "num_loops": args.loops,
                    "base_port": args.base_port,
                    "cluster_startup_delay": args.cluster_startup_delay
                }
            })
            
            all_results.append(summary)
            
            # Print summary for this client count
            print(f"\nResults for {client_count} clients:")
            print(f"  Total Requests: {summary['total_requests']}")
            print(f"  Success Rate: {summary['success_rate']:.2%}")
            print(f"  Average Latency: {summary['avg_latency_ms']:.2f} ms")
            print(f"  Latency Std Dev: {summary['std_latency_ms']:.2f} ms")
            print(f"  Total Duration: {summary['total_duration_s']:.2f} s")
            print(f"  Throughput: {summary['throughput_per_second']:.2f} per second")
            if summary["errors"]:
                print(f"  Errors: {summary['errors']}")
        
        # Print overall summary if multiple client counts were tested
        if len(client_counts) > 1:
            print("\n=== Overall Summary ===")
            for result in all_results:
                clients = result['setup']['num_clients']
                print(f"  {clients} clients: {result['throughput_per_second']:.2f} req/sec, {result['avg_latency_ms']:.2f}ms avg latency")
        
        # Export to JSON if requested
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
        
        if len(client_counts) > 1:
            print(f"Successfully completed {args.transport} cluster scaling test ({min(client_counts)}-{max(client_counts)} clients)")
        else:
            print(f"Successfully completed {args.transport} cluster performance test")
    
    except Exception as e:
        print(f"Error during cluster performance test: {e}")
        sys.exit(1)
    finally:
        # Only stop the cluster if we started it
        if not cluster_was_running:
            print("Stopping cluster...")
            await cluster.stop_cluster()
        else:
            print("Leaving cluster running (was already running when we started)")

if __name__ == "__main__":

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
    from raft_ops.local_ops import LocalCollector 
    from base.collector import Collector
    from base.datatypes import AccountType
    from base.operations import Teller
    from cli.raft_admin_ops import TRANSPORT_CHOICES, nodes_and_helper
    asyncio.run(main())
