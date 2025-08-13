#!/usr/bin/env python
import asyncio
from pathlib import Path
import sys
import time
import json
import argparse
import pickle
import traceback
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
from raft.test_common import test_snapshots

async def main(args):
    cluster = Cluster(base_port=args.base_port)
    started_servers = False
    cluster_ready = False
    ready, reason = await cluster.check_cluster_ready()
    if ready:
        print(f"Cluster reports ready {reason}", flush=True)
        cluster_ready = True
    else:
        print(f"Cluster reports not ready {reason}", flush=True)
        print("will start cluster")

    if not cluster_ready:
        cluster.clear_server_files()
        await cluster.start_servers()
        started_servers = True
        start_time = time.time()
        ready = False
        while time.time() - start_time < 3.0:
            await asyncio.sleep(0.1)
            ready, reason = await cluster.check_cluster_ready()
            if ready:
                break
        if not ready:
            raise Exception('could not start cluster and run election in 3 seconds')

    client_0 = cluster.get_client(0)
    collector = Collector(client_0)
    demo = Demo(collector)
    res = await demo.do_unknown_state_demo()
    
    if started_servers:
        await cluster.stop_servers()
    
if __name__=="__main__":
    parser = argparse.ArgumentParser(description='Raft Cluster Performance Testing Tool')
    parser.add_argument('-b', '--base_port', type=int, default=59090,
                        help='Port number for first node in cluster')
    args = parser.parse_args()
    asyncio.run(main(args))
