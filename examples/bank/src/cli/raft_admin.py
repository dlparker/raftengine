#!/usr/bin/env python

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
                                    tail_server_logs, tail_server_errors, server_admin)
    from raft_ops.local_ops import LocalCollector 
    from cli.test_client_common import add_common_arguments

    asyncio.run(main())
