#!/usr/bin/env python
"""
Unified test client supporting multiple transports.
Works with both stub servers and raft clusters using the same transport.
"""
import asyncio
import argparse
import traceback
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
from raft_ops.local_ops import LocalCollector 
from cli.test_client_common import validate, add_common_arguments

async def main():
    parser = argparse.ArgumentParser(description="Raft Server admin client")
    
    parser.add_argument('command', choices=['getpid', 'start_raft', 'stop', 'status', 'take_power'],
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

    for uri in target_nodes:
        rpc_client = await RPCHelper().rpc_client_maker(uri)
        #print(f"Connecting to {args.transport} server at {uri}")
        server_local_commands = LocalCollector(rpc_client)
        if args.command == 'getpid':
            pid = await server_local_commands.get_pid()
            print(f'Server {uri} pid = {pid}')
        elif args.command == 'start_raft':
            res = await server_local_commands.start_raft()
            print(f'Sent start_raft to server {uri} ')
        elif args.command == 'stop':
            res = await server_local_commands.stop_server()
            print(f'Sent stop command to server {uri} {res}')
        elif args.command == 'take_power':
            res = await server_local_commands.start_campaign()
            print(f'Server {uri} should now start a campaign')
        await rpc_client.close()

if __name__ == "__main__":
    asyncio.run(main())
