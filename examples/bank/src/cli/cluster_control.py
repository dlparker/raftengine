#!/usr/bin/env python
"""
Unified test client supporting multiple transports.
Works with both stub servers and raft clusters using the same transport.
"""
import asyncio
import argparse
import traceback
import subprocess
from pathlib import Path
import sys

this_dir = Path(__file__).resolve().parent
for parent in this_dir.parents:
    if parent.name == 'src':
        if parent not in sys.path:
            sys.path.insert(0, str(parent))
            break
else:
    raise ImportError("Could not find 'src' directory in the path hierarchy")

from cli.raft_admin_ops import TRANSPORT_CHOICES, nodes_and_helper
from cli.raft_admin import server_admin
from raft_ops.local_ops import LocalCollector 
from cli.test_client_common import validate, add_common_arguments

async def start_server(index, uri, transport, RPCHelper, slow_timeouts=True):
    raft_server_path = Path(Path(__file__).parent, 'raft_server.py')
    cmd = [sys.executable, str(raft_server_path), '--transport', transport,
           '--index', str(index)]
    if slow_timeouts:
        cmd.append('--slow_timeouts')
    work_dir = Path('/tmp', f"raft_server.{transport}.{index}")
    stdout_file = Path(work_dir,'server.stdout')
    stderr_file = Path(work_dir,'server.stderr')
    try:
        print(" ".join(cmd))
        with open(stdout_file, 'w') as stdout_f, open(stderr_file, 'w') as stderr_f:
            process = subprocess.Popen(cmd,stdout=stdout_f,stderr=stderr_f, start_new_session=True)
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
        rpc_client = await RPCHelper().rpc_client_maker(uri)
        server_local_commands = LocalCollector(rpc_client)
        pid = await server_local_commands.get_pid()
        print(f'RPC getpid returned {pid}')
    except Exception as e:
        print(f"Error starting server {index}: {traceback.format_exc()}")
        return False
        
    
async def main():
    parser = argparse.ArgumentParser(description="Raft Server Cluster Control")
    
    parser.add_argument('command', choices=['start', 'getpid', 'start_raft', 'stop', 'status', 'take_power'],
                        help='Command to execute')
    parser.add_argument('--transport', '-t', 
                        required=True,
                        choices=TRANSPORT_CHOICES,
                        help='Transport mechanism to use')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--index', '-i', type=int,
                        help='Cluster node index to target') 
    group.add_argument('--all', '-a', action='store_true',
                        help='Do operation on all nodes')
    
    args = parser.parse_args()

    nodes, RPCHelper = nodes_and_helper(args.transport, base_port=50050, node_count=3)
    if args.all:
        target_nodes = nodes
        if args.command == 'take_power':
            parser.error("Cowardly refusing to run take_power on all nodes")
    else:
        target_nodes = [nodes[args.index],]

    if args.command == "start":
        for node_index, uri in enumerate(target_nodes):
            await start_server(node_index, uri, args.transport, RPCHelper)
    else:
        await server_admin(target_nodes, args.command, RPCHelper)
        

if __name__ == "__main__":
    asyncio.run(main())
