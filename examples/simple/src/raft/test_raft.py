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
from base.validator import Validator

async def main(args):

    cluster = Cluster(transport=args.transport, base_port=args.base_port, log_type=args.log_type)
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

    vt = Validator(collector)
    expected = await vt.do_test()
    print(f'test complete, returned {expected}')
    if started_servers:
        await cluster.stop_servers()
    
    
if __name__=="__main__":
    parser = argparse.ArgumentParser(description='Raft Cluster Performance Testing Tool')
    parser.add_argument('-b', '--base_port', type=int, default=59090,
                        help='Port number for first node in cluster')
    parser.add_argument('--transport', '-t', 
                        choices=['astream', 'aiozmq', 'grpc'],
                        default='aiozmq',
                        help='Transport mechanism to use')
    parser.add_argument('--log-type', '-l',
                        choices=['memory', 'sqlite', 'lmdb', 'hybrid'],
                        default='memory',
                        help='Log storage type to use')
    args = parser.parse_args()
    asyncio.run(main(args))
