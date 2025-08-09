#!/usr/bin/env python
import asyncio
from pathlib import Path
import sys
import time
import json
import pickle
import argparse
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
    print(f'validator complete, returned {expected}')
        
    print('Basic functions worked, testing snapshot operations')
    # note that doing this to the leader will cause it to transfer power, so if we run
    # this script twice in a row with a running cluster, it may see a different leader
    # on the second run.
    pre_snap_a_value = await collector.counter_add('a', 0)
    pre_stats = json.loads(await cluster.direct_command(cluster.node_uris[0], 'log_stats'))
    snapshot_dict = await cluster.direct_command(cluster.node_uris[0], 'take_snapshot')
    post_stats = json.loads(await cluster.direct_command(cluster.node_uris[0], 'log_stats'))
    post_snap_a_value = await collector.counter_add('a', 1)
    if snapshot_dict['index'] != pre_stats['last_index']:
        if started_servers:
            try:
                await cluster.stop_servers()
            except:
                pass
            finally:
                raise Exception(f"Expected snapshot index {snapshot_dict['index']} to eqaul pre_stats['last_index'] not {pre_stats['last_index']}")
    
    # now read the snapshot file and make sure it has the pre value
    await asyncio.sleep(0.3) # make sure it has time to save
    server_props = cluster.get_server_props(0)
    wdir = server_props['local_config'].working_dir
    with open(Path(wdir, 'counters_snapshot.pickle'), 'rb') as f:
        buff = f.read()
    counts = pickle.loads(buff)
    assert counts['a'] == pre_snap_a_value
    assert counts['a'] != post_snap_a_value
    print('reading snapshot file went as expected')
    
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
                        default='sqlite',
                        help='Log storage type to use')
    args = parser.parse_args()
    asyncio.run(main(args))
