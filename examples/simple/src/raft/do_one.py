#!/usr/bin/env python
import asyncio
from pathlib import Path
import sys
import argparse
import traceback
src_dir = Path(__file__).parent.parent
sys.path.insert(0, str(src_dir))
from raftengine.deck.log_control import LogController
log_controller = LogController.make_controller()
from cluster import Cluster
from split_base.collector import Collector
from base.demo import Demo

async def main(args):
    cluster = Cluster(args.transport, args.base_port) 
    uri = cluster.node_uris[0]
    client_0 = cluster.get_client(index=0)
    pid = await client_0.direct_server_command("getpid")
    collector = Collector(client_0)
    print("getting counter 'a', should return 0")
    try:
        res = await collector.counter_add('a', 0)
        if res == 0:
            print("getting counter 'a', returned 0 as expected")
        else:
            print("getting counter 'a', did not return 0 as expected")
    except:
        traceback.print_exc()
    await client_0.close()
    
if __name__=="__main__":
    parser = argparse.ArgumentParser(description='Raft Cluster Sanity Check')
    parser.add_argument('-b', '--base_port', type=int, default=59090,
                        help='Port number for first node in cluster')
    parser.add_argument('--transport', '-t', 
                        choices=['astream', 'aiozmq'],
                        default='aiozmq',
                        help='Transport mechanism to use')
    args = parser.parse_args()
    asyncio.run(main(args))
