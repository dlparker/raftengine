import asyncio
import time
import argparse
from pathlib import Path
import pickle
from split_base.collector import Collector
from ops.admin_common import ClusterBuilder, ClusterFinder, get_client
from ops.cluster_cmd import ClusterCLI
from ops.admin_common import get_server_status, take_snapshot 


async def main(args, run_class_dict):
    f_finder = ClusterFinder(root_dir="/tmp")
    clusters = await f_finder.discover()
    target = "test_local"
    if target not in clusters:
        cb = ClusterBuilder()
        local_servers = cb.build_local(name=target, base_port=50010)
        cb.setup_local_files(local_servers, "/tmp", overwrite=True)
    cli = ClusterCLI()
    await cli.discover_cluster_files(search_dir="tmp")
    await cli.do_select(target)
    status_dict = await cli.get_status()
    cluster_ready = True
    uri_0 = None
    started_servers = False
    for index, status in status_dict.items():
        if status is None:
            cluster_ready = False
            break
        if uri_0 is None:
            uri_0 = status['uri']
            
    if not cluster_ready:
        print('starting cluster')
        default_logging_level = 'info'
        if args.error:
            default_logging_level = 'warning'
        elif args.warning:
            default_logging_level = 'warning'
        elif args.info:
            default_logging_level = 'info'
        elif args.debug:
            default_logging_level = 'debug'
            
        await cli.do_start_servers()
        started_servers = True
        start_time = time.time()
        while time.time() - start_time < 3.0:
            await asyncio.sleep(0.1)
            status_dict = await cli.get_status()
            cluster_ready = True
            for index, status in status_dict.items():
                if status is None:
                    cluster_ready = False
                    break
                if uri_0 is None:
                    uri_0 = status['uri']
                print(f"{index} has leader {status['leader_uri']}")
                if status['leader_uri'] is None:
                    cluster_ready = False
                    break
            if cluster_ready:
                break
        if not cluster_ready:
            raise Exception('could not start cluster and find leader in 3 seconds')

    print(f"getting client to uri {uri_0}")
    client_0 = get_client(uri_0)
    collector = Collector(client_0)

    for name, item in run_class_dict.items():
        print(f"doing {name}")
        run_object = item(collector, cli)
        await run_object.run()
        
    if (started_servers and not args.leave_running) or args.stop_cluster:
        await cli.do_stop_cluster()
        
def do_run_args():
    parser = argparse.ArgumentParser(description='Counters Raft Cluster Operations Test')
    parser.add_argument('-b', '--base_port', type=int, default=50010,
                        help='Port number for first node in cluster')
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument('-l', '--leave-running', action="store_true",
                        help='Leave cluster running at end of test')
    group.add_argument('-s', '--stop-cluster', action="store_true",
                        help='Stop cluster at tend of test even if it was already running')
    group_2 = parser.add_mutually_exclusive_group(required=False)
    group_2.add_argument('-D', '--debug', action='store_true',
                       help="Set global logging level to debug")
    group_2.add_argument('-I', '--info', action='store_true',
                       help="Set global logging level to info")
    group_2.add_argument('-W', '--warning', action='store_true',
                       help="Set global logging level to warning")
    group_2.add_argument('-E', '--error', action='store_true',
                       help="Set global logging level to error, which is the default")
    args = parser.parse_args()
    return args

async def test_snapshots(cli, demo_print=True):

    # snapshot every server, starting with non-leaders than moving to leader
    status_dict = await cli.get_status()
    cluster_ready = True
    order = []
    leader_uri = None
    leader_index = None
    for index, status in status_dict.items():
        if status['is_leader']:
            leader_uri = status['uri']
            leader_index = index
            client = get_client(leader_uri)
            collector = Collector(client)
            continue
        order.append(index)
    order.append(leader_index)
    for index in order:
        status = status_dict[index]
        uri = status['uri']
        if index == leader_index and demo_print:
            print(f"target {uri} is leader, will be demoted! ")
        elif demo_print:
            print(f"target {uri} is NOT leader ")
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
        pre_stats = await get_server_status(uri)
        if demo_print:
            print(f"before snapshot last index is {pre_stats['last_log_index']}")
            print(f"before snapshot applied index is {pre_stats['log_apply_index']}")
        snapshot = await take_snapshot(uri)
        if demo_print:
            print(f"snapshot is {snapshot}")
        post_stats = await get_server_status(uri)
        if demo_print:
            print(f"post sanpshot last_log_index = {post_stats['last_log_index']}, first = {post_stats['first_log_index']}")
            print(f"post snapshot applied index is {pre_stats['log_apply_index']}")
        if snapshot.index != pre_stats['log_apply_index']:
            print(f"pre_stats = \n{pre_stats}")
            print(f"post_stats = \n{post_stats}")
            raise Exception(f"Expected snapshot index {snapshot.index} " \
                            f"to eqaul {pre_stats['applied']} ")
    
        # now read the snapshot file and make sure it has the pre value
        await asyncio.sleep(0.3) # make sure it has time to save
        post_snap_a_value = await collector.counter_add('a', 1)
        wdir = status['working_dir']
        with open(Path(wdir, 'counters_snapshot.pickle'), 'rb') as f:
            buff = f.read()
        counts = pickle.loads(buff)
        assert counts['a'] == pre_snap_a_value
        assert counts['a'] != post_snap_a_value
        print(f'reading server {index} snapshot file went as expected')

    status_dict = await cli.get_status()
    for index, status in status_dict.items():
        print(f"{status['uri']} is_leader={status['is_leader']}")
        
async def test_membership(cluster, demo_print=False):
    pass

        
