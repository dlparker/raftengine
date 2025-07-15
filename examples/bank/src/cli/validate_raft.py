#!/usr/bin/env python
"""
Raft Cluster Validation Tool
Manages a 3-node Raft cluster, runs validation tests against the leader (node 0), and cleans up.
"""
import asyncio
import argparse
import sys
from pathlib import Path

this_dir = Path(__file__).resolve().parent
for parent in this_dir.parents:
    if parent.name == 'src':
        if parent not in sys.path:
            sys.path.insert(0, str(parent))
            break
else:
    raise ImportError("Could not find 'src' directory in the path hierarchy")

# Import existing functionality to reuse
from cli.test_client_common import validate, add_common_arguments

# Import cluster management functions
import cli.control_raft_server as cluster_control

class ClusterManager:
    """Manages a 3-node Raft cluster lifecycle"""
    
    def __init__(self, transport, base_port=50050, slow_timeouts=True):
        self.transport = transport
        self.base_port = base_port
        self.slow_timeouts = slow_timeouts
        self.cluster_nodes = []
        
        # Calculate transport offset and initialize cluster configuration
        transport_offsets = {
            'astream': 0,
            'aiozmq': 100,
            'fastapi': 200,
            'grpc': 300
        }
        
        if transport not in transport_offsets:
            raise ValueError(f"Unsupported transport: {transport}")
            
        port_offset = transport_offsets[transport]
        
        # Initialize server definitions exactly like control_raft_server.py
        cluster_control.server_defs = {}
        for index in range(3):  # 3-node cluster
            port = base_port + port_offset + index  # Sequential ports
            url = f"{transport}://127.0.0.1:{port}"
            work_dir = Path('/tmp', f"raft_server.{transport}.{index}")
            
            cluster_control.server_defs[index] = {
                'url': url,
                'transport': transport,
                'work_dir': work_dir,
                'base_port': base_port + port_offset,
                'args_base_port': base_port,
                'port': port
            }
            self.cluster_nodes.append(url)
    
    async def start_cluster(self) -> bool:
        """Start all 3 servers in the cluster"""
        print(f"Starting {self.transport} cluster on base port {self.base_port}")
        print(f"Cluster nodes: {self.cluster_nodes}")
        
        success_count = 0
        
        # Start servers 1 and 2 first (as per control_raft_server.py logic)
        for index in [1, 2]:
            print(f"Starting server {index}...")
            success = await cluster_control.start_server(
                index, 
                pause=False,  # Don't use pause - let them start immediately
                slow_timeouts=self.slow_timeouts
            )
            if success:
                success_count += 1
            else:
                print(f"Failed to start server {index}")
        
        # Start server 0 last (it will become the leader)
        print("Starting server 0 (leader)...")
        success = await cluster_control.start_server(
            0, 
            pause=False,  # Don't use pause 
            slow_timeouts=self.slow_timeouts
        )
        if success:
            success_count += 1
        else:
            print("Failed to start server 0")
        
        if success_count == 3:
            print("All servers started successfully")
            return True
        else:
            print(f"Only {success_count}/3 servers started successfully")
            # Cleanup partially started cluster
            await self.stop_cluster()
            return False
    
    async def stop_cluster(self) -> bool:
        """Stop all servers in the cluster"""
        print("Stopping cluster...")
        success_count = 0
        
        for index in range(3):
            try:
                success = await cluster_control.stop_server(index)
                if success:
                    success_count += 1
            except Exception as e:
                print(f"Error stopping server {index}: {e}")
        
        print(f"Stopped {success_count}/3 servers")
        return success_count == 3
    
    async def get_cluster_status(self) -> dict:
        """Get status of all cluster nodes"""
        status = {}
        for index in range(3):
            try:
                server_status = await cluster_control.get_server_status(index, self.cluster_nodes)
                status[index] = server_status
            except Exception as e:
                status[index] = {'error': str(e), 'running': False}
        return status
    
    def get_leader_connection_info(self):
        """Get connection info for the leader (node 0)"""
        # Calculate the exact port for node 0
        transport_offsets = {
            'astream': 0,
            'aiozmq': 100,
            'fastapi': 200,
            'grpc': 300
        }
        leader_port = self.base_port + transport_offsets[self.transport]
        return 'localhost', leader_port

async def create_client(transport, host, port):
    """Create the appropriate RPC client (reused from validate_rpc.py)"""
    if transport == 'aiozmq':
        from tx_aiozmq.rpc_client import RPCClient
        return RPCClient(host, port)
    elif transport == 'grpc':
        from tx_grpc.rpc_helper import RPCHelper
        uri = f"grpc://{host}:{port}"
        return await RPCHelper().rpc_client_maker(uri)
    elif transport == 'fastapi':
        from tx_fastapi.rpc_helper import RPCHelper
        uri = f"fastapi://{host}:{port}"
        return await RPCHelper().rpc_client_maker(uri)
    elif transport == 'astream':
        from tx_astream.rpc_helper import RPCHelper
        uri = f"astream://{host}:{port}"
        return await RPCHelper().rpc_client_maker(uri)
    else:
        raise ValueError(f"Unsupported transport: {transport}")

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
    parser.add_argument('--cluster-startup-delay', type=float, default=5.0,
                        help='Delay in seconds to wait for cluster formation (default: 5.0)')
    
    # Add common validation arguments
    add_common_arguments(parser)
    
    args = parser.parse_args()
    
    # Create cluster manager
    cluster = ClusterManager(args.transport, args.base_port, slow_timeouts=True)
    
    try:
        # Start the cluster
        cluster_started = await cluster.start_cluster()
        if not cluster_started:
            print("Failed to start cluster")
            sys.exit(1)
        
        # Wait for cluster formation and leader election
        print(f"Waiting {args.cluster_startup_delay}s for cluster formation...")
        await asyncio.sleep(args.cluster_startup_delay)
        
        # Get leader connection info (node 0)
        leader_host, leader_port = cluster.get_leader_connection_info()
        print(f"Connecting to leader at {leader_host}:{leader_port}")
        
        # Create client connection to leader
        rpc_client = await create_client(args.transport, leader_host, leader_port)
        
        try:
            # Run validation against the leader
            await validate(rpc_client, 
                          mode=args.mode,
                          loops=args.loops,
                          use_random_data=args.random,
                          print_timing=not args.no_timing,
                          json_output=args.json_output)
            
            print(f"Successfully completed {args.transport} cluster validation")
            
        finally:
            # Close client connection
            if hasattr(rpc_client, 'close'):
                await rpc_client.close()
                await asyncio.sleep(0.2)
    
    except Exception as e:
        print(f"Error during cluster validation: {e}")
        sys.exit(1)
    finally:
        # Always stop the cluster
        await cluster.stop_cluster()

if __name__ == "__main__":
    asyncio.run(main())
