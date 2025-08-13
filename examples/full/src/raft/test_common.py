import asyncio
from pathlib import Path
import pickle
from split_base.collector import Collector

async def test_snapshots(cluster, demo_print=False):

    for index in range(3):
        client = cluster.get_client(index)
        collector = Collector(client)
        leader_uri = await cluster.find_leader()
        if leader_uri == client.get_uri() and demo_print:
            print(f"target {client.get_uri()} is leader ")
        elif demo_print:
            print(f"target {client.get_uri()} is NOT leader ({leader_uri})")
        # the purpose of this call is to ensure that logs propogation
        # completes after any prior pass through the loop. The last
        # counter update call may not have reached the "apply" stage
        # of propogation yet since that is delayed until the leader
        # notifies the followers of the commit index update, which
        # will only happend with additional log updates or heartbeats.
        # Since we are running with extremely long timeouts heartbeats
        # are not going to happend, so we need to prod things along.
        # The counter logic doesn't do anything special with an add 0
        # command, it is an actual add, but it doesn't change the value
        # of the counter. Thus it serves as a nice way to flush the
        # last value changing update.
        await collector.counter_add('a', 0)
        if demo_print:
            print(f"doing snapshot on server {index}")
        pre_snap_a_value = await collector.counter_add('a', 0)
        pre_stats = await cluster.direct_command(cluster.node_uris[index], 'status')
        if demo_print:
            print(f"before snapshot last index is {pre_stats['last_log_index']}")
            print(f"before snapshot applied index is {pre_stats['log_apply_index']}")
        snapshot_dict = await cluster.direct_command(cluster.node_uris[index], 'take_snapshot')
        if demo_print:
            print(f"snapshot is {snapshot_dict}")
        post_stats = await cluster.direct_command(cluster.node_uris[index], 'status')
        if demo_print:
            print(f"post sanpshot last_log_index = {post_stats['last_log_index']}, first = {post_stats['first_log_index']}")
            print(f"post snapshot applied index is {pre_stats['log_apply_index']}")
        if snapshot_dict['index'] != pre_stats['log_apply_index']:
            print(f"pre_stats = \n{pre_stats}")
            print(f"post_stats = \n{post_stats}")
            raise Exception(f"Expected snapshot index {snapshot_dict['index']} " \
                            f"to eqaul {pre_stats['applied']} ")
    
        # now read the snapshot file and make sure it has the pre value
        await asyncio.sleep(0.3) # make sure it has time to save
        server_props = cluster.get_server_props(index)
        post_snap_a_value = await collector.counter_add('a', 1)
        wdir = server_props['local_config'].working_dir
        with open(Path(wdir, 'counters_snapshot.pickle'), 'rb') as f:
            buff = f.read()
        counts = pickle.loads(buff)
        assert counts['a'] == pre_snap_a_value
        assert counts['a'] != post_snap_a_value
        print(f'reading server {index} snapshot file went as expected')

async def test_membership(cluster, demo_print=False):
    pass

        
