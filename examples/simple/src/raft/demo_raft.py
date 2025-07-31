#!/usr/bin/env python
import asyncio
from pathlib import Path
import sys
import time
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
    cluster = Cluster(transport=args.transport, base_port=args.base_port)
    started_servers = False
    cluster_ready = False
    ready, reason = await cluster.check_cluster_ready()
    if ready:
        print(f"Cluster reports ready {reason}", flush=True)
        cluster_ready = True
    else:
        print(f"Cluster reports not ready {reason}", flush=True)
        if "take_power" in reason:
            await cluster.elect_leader(0)
            ready, reason = await cluster.check_cluster_ready()
            if not ready:
                raise Exception('cluster running but did not elect a leader')
            cluster_ready = True
        else:
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
            if 'take_power' in reason:
                print('cluster running, election needed')
                await cluster.elect_leader(0)
        if not ready:
            raise Exception('could not start cluster and run election in 3 seconds')

    # we get a client to node 0, which may not be the leader,
    # trusting in redirect logic to send us to the right node
    client_0 = cluster.get_client(0)
    collector = Collector(client_0)
    ct = Demo(collector)
    res = await ct.do_unknown_state_demo()
    if started_servers:
        await cluster.stop_servers()
    await client_0.close()
    
if __name__=="__main__":
    parser = argparse.ArgumentParser(description='Raft Cluster Performance Testing Tool')
    parser.add_argument('-b', '--base_port', type=int, default=59090,
                        help='Port number for first node in cluster')
    parser.add_argument('--transport', '-t', 
                        choices=['astream', 'aiozmq', 'fastapi','grpc'],
                        default='aiozmq',
                        help='Transport mechanism to use')
    args = parser.parse_args()
    asyncio.run(main(args))
