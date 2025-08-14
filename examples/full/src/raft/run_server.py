#!/usr/bin/env python
import asyncio
import argparse
import shutil
from pathlib import Path
from raftengine.api.deck_config import ClusterInitConfig, LocalConfig
from raftengine.deck.log_control import LogController

log_controller = LogController.make_controller()
log_controller.set_default_level('warning')
log_controller.set_logger_level('Elections', 'info')

import sys
src_dir = Path(__file__).parent.parent
logs_dir = Path(src_dir, 'logs')
sys.path.insert(0, str(logs_dir))
src_dir = Path(__file__).parent.parent
sys.path.insert(0, str(src_dir))
from raft.raft_server import RaftServer


async def main(args):
    nodes = []
    for pnum in range(args.base_port, args.base_port + 3):
        nodes.append(f"as_raft://127.0.0.1:{pnum}")

    heartbeat_period=0.01
    election_timeout_min=0.10
    election_timeout_max=0.35

    initial_cluster_config = ClusterInitConfig(node_uris=nodes,
                                               heartbeat_period=heartbeat_period,
                                               election_timeout_min=election_timeout_min,
                                               election_timeout_max=election_timeout_max,
                                               use_pre_vote=False,
                                               use_check_quorum=True,
                                               max_entries_per_message=10,
                                               use_dynamic_config=False)

    work_dir = Path('/tmp', f"simple_raft_server.{args.index}")
    if not work_dir.exists():
        work_dir.mkdir()

        
    uri = nodes[args.index]
    local_config = LocalConfig(uri=uri, working_dir=work_dir)
    server = RaftServer(initial_cluster_config,
                        LocalConfig(uri=uri, working_dir=work_dir))
    try:
        await server.start()
        while not server.stopped:
            try:
                await asyncio.sleep(0.01)
            except asyncio.CancelledError:
                await server.stop()
                break
                
                
    except KeyboardInterrupt:
        print("Cntl-c, trying to stop server", flush=True)
        await server.stop()
        start_time = time.time() 
        while not server.stopped and time.time() - start_time < 2.0:
            await asyncio.sleep(0.01)
        if not server.stopped:
            raise Exception('could not stop server in two seconds')
        
if __name__=="__main__":
    import uvloop;
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    
    parser = argparse.ArgumentParser(description='Counters Raft Server')
    parser.add_argument('-b', '--base_port', type=int, default=50090,
                        help='Port number for first node in cluster')
    parser.add_argument('-i', '--index', type=int, default=0, required=True,
                        help='Index from cluster base port, also index into node list')
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument('-D', '--debug', action='store_true',
                       help="Set global logging level to debug")
    group.add_argument('-I', '--info', action='store_true',
                       help="Set global logging level to info")
    group.add_argument('-W', '--warning', action='store_true',
                       help="Set global logging level to warning")
    group.add_argument('-E', '--error', action='store_true',
                       help="Set global logging level to error, which is the default")
    parser.add_argument('-j', '--join', action='store_true',
                        help='Join existing cluster as new node at the index specified by -i')
    # Parse arguments
    args = parser.parse_args()
    args = parser.parse_args()
    if args.warning:
        log_controller.set_default_level('warning')
    elif args.info:
        log_controller.set_default_level('info')
    if args.debug:
        log_controller.set_default_level('debug')
    asyncio.run(main(args))
