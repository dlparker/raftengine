#!/usr/bin/env python
import asyncio
import argparse
from pathlib import Path
import subprocess
import sys
import json
import time
from datetime import datetime
import traceback

# Initialize logging controller
from raftengine.deck.log_control import LogController
log_controller = LogController.make_controller()

src_dir = Path(__file__).parent.parent
logs_dir = Path(src_dir, 'logs')
sys.path.insert(0, str(logs_dir))
src_dir = Path(__file__).parent.parent
sys.path.insert(0, str(src_dir))

from raft.cluster import Cluster

async def setup_and_validate_cluster(cluster):
    try:
        print(f"Cluster setup starting")
        print("Clearing server files...")
        cluster.clear_server_files()
            
        print("Starting servers...")
        await cluster.start_servers()

        start_time = time.time()
        while time.time() - start_time < 1.0:
            # Check if leader needs to be elected
            cluster_ready, status_msg = await cluster.check_cluster_ready()
            if not cluster_ready:
                if "No server reports that it is leader" in status_msg:
                    print("No leader detected, electing leader on server 0...")
                    await cluster.elect_leader(0)
                else:
                    raise Exception(f"Cluster not ready: {status_msg}")
                
    except Exception as e:
        print(f"Cluster setup failed")
    return False

async def stop_cluster(cluster):
    await cluster.stop_servers()

async def run_client_test(client_count, loops_per_client, warmup, transport, base_port, temp_json_file):
    """Run a single client test and return the results"""
    client_runner_path = Path(__file__).parent / 'client_runner.py'
    
    cmd = [
        sys.executable, str(client_runner_path),
        "--clients", str(client_count),
        "-l", str(loops_per_client), 
        "--warmup", str(warmup),
        "-t", transport,
        "-b", str(base_port),
        "--json-output", str(temp_json_file)
    ]
    
    print(f"Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)  # 5 minute timeout
        
        if result.returncode != 0:
            error_msg = f"Client test failed with exit code {result.returncode}"
            if result.stderr:
                error_msg += f": {result.stderr}"
            raise Exception(error_msg)
        
        # Load the JSON results
        if temp_json_file.exists():
            with open(temp_json_file, 'r') as f:
                test_results = json.load(f)
            temp_json_file.unlink()  # Clean up temp file
            return test_results
        else:
            raise Exception("No JSON output file created by client_runner")
            
    except subprocess.TimeoutExpired:
        raise Exception("Client test timed out after 5 minutes")
    except Exception as e:
        raise Exception(f"Client test execution failed: {e}")

async def main():
    parser = argparse.ArgumentParser(description='Raft Performance Test Runner - Manages full test sequences')
    
    parser.add_argument("-x", "--min-clients", type=int, required=True, help="Minimum number of clients for range testing")
    parser.add_argument("-y", "--max-clients", type=int, required=True,
                        help="Maximum number of clients for range testing")
    parser.add_argument("-s", "--clients-step", type=int,
                        help="Increase in client count per step", default=1)
    parser.add_argument("-l", "--loops", type=int, default=100, help="Total loops for each run, distributed across clients")
    parser.add_argument("-w", "--warmup", type=int, default=10, help="Number of warmup loops per client (default: 10)")
    parser.add_argument("-j", "--json-output", type=bool, help="Export results to JSON file")
    parser.add_argument('--transport', '-t', 
                        choices=['astream', 'aiozmq', 'grpc'],
                        default='aiozmq',
                        help='Transport mechanism to use')
    parser.add_argument('--log-type', 
                        choices=['memory', 'sqlite', 'lmdb', 'hybrid'],
                        default='memory',
                        help='Log storage type to use')
    parser.add_argument('-b', '--base_port', type=int, default=55555,
                        help='Port number for first node in cluster')
    
    args = parser.parse_args()
    
    # Initialize cluster
    cluster = Cluster(transport=args.transport, base_port=args.base_port, log_type=args.log_type)
    
    # Prepare output structure
    test_start_time = datetime.now()
    output_data = {
        "test_specification": {
            "transport": args.transport,
            "log_type": args.log_type,
            "client_range": {"min": args.min_clients, "max": args.max_clients, "step": args.clients_step},
            "loops_total": args.loops,
            "warmup_loops": args.warmup,
            "base_port": args.base_port,
            "test_timestamp": test_start_time.isoformat()
        },
        "individual_test_results": [],
        "aggregate_summary": {
            "total_tests_run": 0,
            "successful_tests": 0,
            "failed_tests": 0,
            "total_duration_seconds": 0
        }
    }
    
    try:
        print(f"Starting performance test sequence:")
        print(f"  Transport: {args.transport}")
        print(f"  Log type: {args.log_type}")
        print(f"  Client range: {args.min_clients} to {args.max_clients} (step {args.clients_step})")
        print(f"  Total loops per test: {args.loops}")
        print(f"  Warmup loops per client: {args.warmup}")
        print(f"  Base port: {args.base_port}")
        
        temp_json_file = Path(f"/tmp/client_runner_temp_{int(time.time())}.json")
        
        cluster_running = False
        for client_count in range(args.min_clients, args.max_clients + 1, args.clients_step):
            test_start = time.time()
            print(f"\n=== Testing with {client_count} clients ===")
            
            try:
                # Setup cluster for this test
                await setup_and_validate_cluster(cluster)
                cluster_running = True
                # Calculate loops per client
                loops_per_client = max(1, args.loops // client_count)
                
                # Run the client test
                test_result = await run_client_test(client_count, loops_per_client, args.warmup, 
                                                    args.transport, args.base_port, temp_json_file)
                print(json.dumps(test_result, indent=2))
                
                # Record successful test
                output_data["individual_test_results"].append({
                    "client_count": client_count,
                    "loops_per_client": loops_per_client,
                    "result": test_result,
                    "test_duration_seconds": time.time() - test_start
                })
                
                output_data["aggregate_summary"]["successful_tests"] += 1
                print(f"✓ Test with {client_count} clients completed successfully")

                await stop_cluster(cluster)
                cluster_running = False
                await asyncio.sleep(0.1)
            except Exception as e:
                print(f"✗ Test with {client_count} clients failed: {e}")
                output_data["individual_test_results"].append({
                    "client_count": client_count,
                    "loops_per_client": loops_per_client if 'loops_per_client' in locals() else 0,
                    "error": str(e),
                    "test_duration_seconds": time.time() - test_start
                })
                output_data["aggregate_summary"]["failed_tests"] += 1
            
            output_data["aggregate_summary"]["total_tests_run"] += 1
            
            # Small delay between tests
            await asyncio.sleep(1.0)
        
    except Exception as e:
        print(f"Test sequence failed: {e}")
        traceback.print_exc()
    
    finally:
        if cluster_running:
            try:
                print("\nStopping cluster...")
                await cluster.stop_servers()
            except Exception as e:
                print(f"Error stopping cluster: {e}")
        
        # Finalize output
        test_end_time = datetime.now()
        output_data["aggregate_summary"]["total_duration_seconds"] = (test_end_time - test_start_time).total_seconds()
        
        # Write final results
        try:
            with open(args.json_output, 'w') as f:
                json.dump(output_data, f, indent=2)
            print(f"\nResults written to {args.json_output}")
            
            # Print summary
            summary = output_data["aggregate_summary"]
            print(f"\nTest Summary:")
            print(f"  Total tests: {summary['total_tests_run']}")
            print(f"  Successful: {summary['successful_tests']}")
            print(f"  Failed: {summary['failed_tests']}")
            print(f"  Total duration: {summary['total_duration_seconds']:.2f} seconds")
            
        except Exception as e:
            print(f"Error writing results: {e}")
            # Try to at least print the results
            print("Results:")
            print(json.dumps(output_data, indent=2))

if __name__=="__main__":
    asyncio.run(main())
    
