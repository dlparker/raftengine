#!/usr/bin/env python
"""
Raft Cluster Validation Tool
Manages a 3-node Raft cluster, runs validation tests against the leader (node 0), and cleans up.
"""

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

async def main():
    parser = argparse.ArgumentParser(
        description='Raft Cluster Validation Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --transport grpc demo
  %(prog)s --transport aiozmq test --loops 10 --json-output cluster_results.json
  %(prog)s --transport fastapi demo --random --loops 3

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
    
    # Add common validation arguments
    add_common_arguments(parser)
    
    args = parser.parse_args()
    
    # Create cluster manager
    cluster = ClusterManager(args.transport, args.base_port, slow_timeouts=True)
    
    # Check if cluster is already running
    leader_uri = cluster.cluster_nodes[0]
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

            # Get leader URI (node 0)
            leader_uri = cluster.get_leader_uri()
            print(f"Connecting to leader at {leader_uri}")

        except Exception as e:
            print(f"Error during cluster setup: {traceback.format_exc()}")
            sys.exit(1)
        finally:
            print("Stopping cluster...")
            await cluster.stop_cluster()

    # Create client connection to leader
    logger = logging.getLogger('raft_ops.RaftClient')
    logger.debug('starting with client of %s', leader_uri)
    logger2 = logging.getLogger('Deck')
    logger2.debug('starting with client of %s', leader_uri)
    rpc_client = await cluster.RPCHelper().rpc_client_maker(leader_uri)
    logger.debug('starting with client of %s', leader_uri)
    await asyncio.sleep(0.1)
    try:
        # Run validation against the leader
        await validate(rpc_client, 
                       mode=args.mode,
                       loops=args.loops,
                       use_random_data=args.random,
                       print_timing=not args.no_timing,
                       json_output=args.json_output,
                       rpc_helper=cluster.RPCHelper)

        print(f"Successfully completed {args.transport} cluster validation")
        exit_value = 0
    except Exception as e:
        print(f"Error during cluster validation: {traceback.format_exc()}")
        exit_value = 1
    finally:
        await rpc_client.close()
        await asyncio.sleep(0.2)
        # Only stop the cluster if we started it
        if not cluster_was_running:
            print("Stopping cluster...")
            await cluster.stop_cluster()
        else:
            print("Leaving cluster running (was already running when we started)")
    raise SystemExit(exit_value)

if __name__ == "__main__":
    import asyncio
    import argparse
    import sys
    import traceback
    import logging
    from pathlib import Path
    from raftengine.deck.log_control import LogController
    # setup LogControl before importing any modules that might initialize it first
    LogController.controller = None
    log_control = LogController.make_controller()
    log_control.set_default_level('DEBUG')

    this_dir = Path(__file__).resolve().parent
    for parent in this_dir.parents:
        if parent.name == 'src':
            if parent not in sys.path:
                sys.path.insert(0, str(parent))
                break
    else:
        raise ImportError("Could not find 'src' directory in the path hierarchy")

    from raft_ops.local_ops import LocalCollector 
    from raft_ops.raft_client import RaftClient # this is just to get the logger registered
    from cli.raft_admin_ops import TRANSPORT_CHOICES, nodes_and_helper, server_admin
    # Import existing functionality to reuse
    from cli.test_client_common import validate, add_common_arguments
    asyncio.run(main(), debug=True)
