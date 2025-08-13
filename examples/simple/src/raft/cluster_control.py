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

    
    
    parser.add_argument('command', choices=['start', 'stop', 'status', 'getpid'],
                        help='Command to execute')
    parser.add_argument('-b', '--base_port', type=int, default=50090,
                        help='Port number for first node in cluster')
    group = parser.add_mutually_exclusive_group(required=False)
    args = parser.parse_args()

    cluster = Cluster(base_port=args.base_port)
    nodes = cluster.node_uris
    target_nodes = nodes
    if args.command == "start":
        await cluster.start_servers(targets=target_nodes)

    async def direct_command(uri, *args):
        try:
            res = await cluster.direct_command(uri, *args)
        except TimeoutError:
            res = f"Direct command to {uri} timed out, target probably not running"
        return res
    
    if args.command in ['stop', 'status', 'getpid']:
        for uri in target_nodes:
            result = await direct_command(uri, args.command)
            if args.command in ("status"):
                print(json.dumps(result, indent=2))
            else:
                print(result)

if __name__=="__main__":
    asyncio.run(main())
