import asyncio
import time
import argparse
from pathlib import Path
import pickle
from split_base.collector import Collector
from cluster import Cluster

async def main(args, run_class_dict):
    cluster = Cluster(base_port=args.base_port)
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
        default_logging_level = 'info'
        if args.error:
            default_logging_level = 'warning'
        elif args.warning:
            default_logging_level = 'warning'
        elif args.info:
            default_logging_level = 'info'
        elif args.debug:
            default_logging_level = 'debug'
            
        await cluster.start_servers(default_logging_level=default_logging_level)
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

    client_0 = cluster.get_client(0)
    collector = Collector(client_0)

    for name, item in run_class_dict.items():
        print(f"doing {name}")
        run_object = item(collector)
        await run_object.run()
        
    if (started_servers and not args.leave_running) or args.stop_cluster:
        await cluster.stop_servers()

def do_run_args():
    parser = argparse.ArgumentParser(description='Counters Raft Cluster Basic Test')
    parser.add_argument('-b', '--base_port', type=int, default=50000,
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
        
