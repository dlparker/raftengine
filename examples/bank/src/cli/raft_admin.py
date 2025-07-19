#!/usr/bin/env python
"""
Unified test client supporting multiple transports.
Works with both stub servers and raft clusters using the same transport.
"""
import asyncio
import argparse
import traceback
import json
from pathlib import Path
import sys
from pprint import pprint

this_dir = Path(__file__).resolve().parent
for parent in this_dir.parents:
    if parent.name == 'src':
        if parent not in sys.path:
            sys.path.insert(0, str(parent))
            break
else:
    raise ImportError("Could not find 'src' directory in the path hierarchy")

from raftengine.deck.log_control import LogController
# setup LogControl before importing any modules that might initialize it first
LogController.controller = None
log_control = LogController.make_controller()

from cli.raft_admin_ops import (TRANSPORT_CHOICES, nodes_and_helper, stop_server,
                                tail_server_logs, tail_server_errors)
from raft_ops.local_ops import LocalCollector 
from cli.test_client_common import validate, add_common_arguments

async def server_admin(target_nodes, command, RPCHelper):
    
    for uri in target_nodes:
        try:
            try:
                rpc_client = await RPCHelper().rpc_client_maker(uri)
                server_local_commands = LocalCollector(rpc_client)
                res = await server_local_commands.get_pid()
            except Exception as e:
                print(f'Server {uri} not reachable, probably not running "{e}"')
                try:
                    await rpc_client.close()
                except:
                    pass
                continue
            if command == 'getpid':
                pid = await server_local_commands.get_pid()
                print(f'Server {uri} pid = {pid}')
            elif command == 'start_raft':
                res = await server_local_commands.start_raft()
                print(f'Sent start_raft to server {uri} ')
            elif command == 'stop':
                await stop_server(rpc_client, target_nodes)
            elif command == 'status':
                try:
                    status = await server_local_commands.get_status()
                    print(f'Server {uri}')
                    pprint(status)
                except:
                    traceback.print_exc()
                    running = False
                    print(f'Server {uri} not reachable, probably not running')
            elif command == 'take_power':
                res = await server_local_commands.start_campaign()
                print(f'Server {uri} should now start a campaign')
            elif command == 'get_log_config':
                try:
                    config = await server_local_commands.get_logging_dict()
                    res = json.dumps(config, indent=4)
                    print(res)
                except:
                    traceback.print_exc()
                    running = False
                    print(f'Server {uri} not reachable, probably not running')
            elif command == 'set_logging_level':
                try:
                    await server_local_commands.set_logging_level("debug", [])
                    print("set to debug")
                except:
                    traceback.print_exc()
                    running = False
                    print(f'Server {uri} not reachable, probably not running')
            elif command == 'tail':
                await tail_server_logs(rpc_client, target_nodes)
            elif command == 'tail_errors':
                await tail_server_errors(rpc_client, target_nodes)
            await rpc_client.close()
        except:
            traceback.print_exc()
            print(f'could not complete command for {uri}')

async def main():
    parser = argparse.ArgumentParser(description="Raft Server admin client")
    
    parser.add_argument('command', choices=['getpid', 'start_raft', 'stop',
                                            'status', 'take_power', 'get_log_config',
                                            "set_logging_level", "tail", "tail_errors"],
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

    await server_admin(target_nodes, args.command, RPCHelper)

if __name__ == "__main__":
    asyncio.run(main())
