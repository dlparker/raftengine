#!/usr/bin/env python
import asyncio
import argparse
import json
from pathlib import Path
import sys
src_dir = Path(__file__).parent.parent
logs_dir = Path(src_dir, 'logs')
sys.path.insert(0, str(logs_dir))
src_dir = Path(__file__).parent.parent
sys.path.insert(0, str(src_dir))

from raftengine.deck.log_control import LogController
log_controller = LogController.make_controller()
from cluster import Cluster
from split_base.collector import Collector
from base.demo import Demo

async def main():

    epilog = "The command parameter determines which action to take regarding the cluster."
    epilog += "\n\n'start', 'stop', 'status', and 'getpid', should be obvious"

    
    parser = argparse.ArgumentParser(description="Counters Raft Server Cluster Control",
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog=epilog)

    
    
    parser.add_argument('command', choices=['start', 'stop', 'status', 'getpid', 'dump_status',
                                            'take_power', 'get_leader',
                                            'get_logging_dict', 'set_debug_logging',
                                            'set_info_logging', 'set_warning_logging', 'set_error_logging'],
                        help='Command to execute')
    parser.add_argument('-b', '--base_port', type=int, default=50090,
                        help='Port number for first node in cluster')
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument('--index', '-i', type=int,
                        help='Cluster node index to target') 
    group.add_argument('--all', '-a', action='store_true', default=True,
                        help='Do operation on all nodes')
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

    cluster = Cluster(base_port=args.base_port)
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
        
    if args.command == "start":
        await cluster.start_servers(targets=target_nodes, default_logging_level=logging_level)

    async def direct_command(uri, *args):
        try:
            res = await cluster.direct_command(uri, *args)
        except TimeoutError:
            res = f"Direct command to {uri} timed out, target probably not running"
        return res
    
    if args.command in ['stop', 'status', 'getpid', f'dump_status', 'take_power',
                        'get_logging_dict']:
        for uri in target_nodes:
            result = await direct_command(uri, args.command)
            if args.command in ("status", "dump_status", "get_logging_dict"):
                print(json.dumps(result, indent=2))
            else:
                print(result)
    elif args.command == "get_leader":
        uri_0  = nodes[0]
        status = await direct_command(uri_0, 'status')
        if not isinstance(status, dict):
            print(f"error: {status}")
        else:
            leader = None
            if status['leader_uri']:
                print(status['leader_uri'])
            else:
                print('error: no leader')
            
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
