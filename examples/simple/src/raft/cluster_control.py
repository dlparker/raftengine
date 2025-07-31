#!/usr/bin/env python
import asyncio
import argparse
import json
from pathlib import Path
import sys
src_dir = Path(__file__).parent.parent
sys.path.insert(0, str(src_dir))
from raftengine.deck.log_control import LogController
log_controller = LogController.make_controller()
from run_tools import Cluster
from split_base.collector import Collector
from base.demo import Demo
from rpc.run_tools import RunTools

async def main():

    epilog = "The command parameter determines which action to take regarding the cluster."
    epilog += "\n\n'start', 'stop', 'status', and 'getpid', should be obvious"

    
    parser = argparse.ArgumentParser(description="Counters Raft Server Cluster Control",
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog=epilog)

    
    
    parser.add_argument('command', choices=['start', 'stop', 'status', 'getpid', 'dump_status',
                                            'start_paused', 'start_raft', 'take_power',
                                            'get_logging_dict', 'set_debug_logging',
                                            'set_info_logging', 'set_warning_logging', 'set_error_logging'],
                        help='Command to execute')
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument('--index', '-i', type=int,
                        help='Cluster node index to target') 
    group.add_argument('--all', '-a', action='store_true', default=True,
                        help='Do operation on all nodes')
    parser.add_argument('-b', '--base_port', type=int, default=50090,
                        help='Port number for first node in cluster')
    parser.add_argument('-f', '--full-start', action='store_true',
                        help='Start raft everywhere and tell server 0 to take power. Only valid with --all and "start"')
    parser.add_argument('--transport', '-t', 
                        choices=['astream', 'aiozmq', 'fastapi','grpc'],
                        default='aiozmq',
                        help='Transport mechanism to use')
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument('-D', '--debug', action='store_true',
                       help="Set global logging level to debug")
    group.add_argument('-I', '--info', action='store_true',
                       help="Set global logging level to info")
    group.add_argument('-W', '--warning', action='store_true',
                       help="Set global logging level to warning")
    group.add_argument('-E', '--error', action='store_true',
                       help="Set global logging level to error, which is the default")
    
    args = parser.parse_args()

    if args.command == 'take_power' and args.index is None:
        parser.error("Cowardly refusing to run take_power on all nodes")

    cluster = Cluster(transport=args.transport, base_port=args.base_port)
    nodes = cluster.node_uris
    if args.index is None:
        target_nodes = nodes
    else:
        target_nodes = [nodes[args.index],]

    logging_level = 'error'
    if args.warning:
        logging_level = 'warning'
    if args.info:
        logging_level = 'info'
    if args.debug:
        logging_level = 'debug'
        
    start_paused = False
    if args.command == "start_paused":
        start_paused = True 
    if args.command == "start" or args.command == "start_paused":
        await cluster.start_servers(targets=target_nodes, start_paused=start_paused, default_logging_level=logging_level)

    async def direct_command(uri, *args):
        try:
            res = await cluster.direct_command(uri, *args)
        except TimeoutError:
            res = f"Direct command to {uri} timed out, target probably not running"
        return res
    
    if args.command == "start" and args.full_start and args.all:
        for uri in nodes:
            await cluster.direct_command(uri, "start_raft")
        u0  = nodes[0]
        await asyncio.sleep(0.01)
        await direct_command(uri, "take_power")
    if args.command in ['stop', 'status', 'getpid', f'dump_status', 'start_raft', 'take_power', 'get_logging_dict']:
        for uri in target_nodes:
            result = await direct_command(uri, args.command)
            if args.command in ("status", "dump_status"):
                print(json.dumps(result, indent=2))
            else:
                print(result)
    elif args.command == 'set_debug_logging':
        for uri in target_nodes:
            print(await direct_command(uri, "set_logging_level", 'debug'))
    elif args.command == 'set_info_logging':
        for uri in target_nodes:
            print(await direct_command(uri, "set_logging_level", 'info'))
    elif args.command == 'set_warning_logging':
        for uri in target_nodes:
            print(await direct_command(uri, "set_logging_level", 'warning'))
    elif args.command == 'set_error_logging':
        for uri in target_nodes:
            print(await direct_command(uri, "set_logging_level", 'error'))

if __name__=="__main__":
    asyncio.run(main())
