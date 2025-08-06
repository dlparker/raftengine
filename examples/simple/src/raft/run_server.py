#!/usr/bin/env python
import asyncio
import argparse
import shutil
from pathlib import Path
from raftengine.api.deck_config import ClusterInitConfig, LocalConfig
from raftengine.deck.log_control import LogController

log_controller = LogController.make_controller()
log_controller.set_default_level('warning')
#log_controller.set_logger_level('Leader', 'info')
#log_controller.set_logger_level('Follower', 'info')
#log_controller.set_logger_level('HybridLog', 'debug')
#log_controller.set_logger_level('HybridLog.sqlite_writer', 'debug')

import sys
src_dir = Path(__file__).parent.parent
logs_dir = Path(src_dir, 'logs')
sys.path.insert(0, str(logs_dir))
src_dir = Path(__file__).parent.parent
sys.path.insert(0, str(src_dir))
from raft.raft_server import RaftServer
from rpc.run_tools import RunTools as RPCRunTools


async def main(args):
    nodes = []
    for pnum in range(args.base_port, args.base_port + 3):
        nodes.append(f"{args.transport}://127.0.0.1:{pnum}")

    heartbeat_period=10000
    election_timeout_min=20000
    election_timeout_max=20001

    initial_cluster_config = ClusterInitConfig(node_uris=nodes,
                                               heartbeat_period=heartbeat_period,
                                               election_timeout_min=election_timeout_min,
                                               election_timeout_max=election_timeout_max,
                                               use_pre_vote=False,
                                               use_check_quorum=True,
                                               max_entries_per_message=10,
                                               use_dynamic_config=False)

    work_dir = Path('/tmp', f"counters_raft_server.{args.transport}.{args.index}")
    if args.clear_data:
        # already checked for --tell-me-twice above
        if work_dir.exists():
            shutil.rmtree(work_dir)
        work_dir.mkdir()
    elif not work_dir.exists():
        work_dir.mkdir()
    uri = nodes[args.index]
    local_config = LocalConfig(uri=uri, working_dir=work_dir)
    rpc_run_tools = RPCRunTools(args.transport)
    server = RaftServer(initial_cluster_config,
                        LocalConfig(uri=uri, working_dir=work_dir),
                        rpc_run_tools.get_server_class(), rpc_run_tools.get_client_class(),
                        log_type=args.log_type
                        )
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
    parser.add_argument('-i', '--index', type=int, required=True,
                        help='Index of this server node in cluster node list')
    parser.add_argument('--clear-data', action='store_true',
                        help='Clear Raft log and bank db, must be used with --tell-me-twice')
    parser.add_argument('--tell-me-twice', action='store_true',
                        help='Really do the dangerous thing requested')
    parser.add_argument('--transport', '-t', 
                        choices=['astream', 'aiozmq', 'grpc'],
                        default='aiozmq',
                        help='Transport mechanism to use')
    parser.add_argument('--log-type', '-l',
                        choices=['memory', 'sqlite', 'lmdb', 'hybrid'],
                        default='sqlite',
                        help='Log storage type to use')
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument('-D', '--debug', action='store_true',
                       help="Set global logging level to debug")
    group.add_argument('-I', '--info', action='store_true',
                       help="Set global logging level to info")
    group.add_argument('-W', '--warning', action='store_true',
                       help="Set global logging level to warning")
    group.add_argument('-E', '--error', action='store_true',
                       help="Set global logging level to error, which is the default")
    # Parse arguments
    args = parser.parse_args()
    if args.warning:
        log_controller.set_default_level('warning')
    elif args.info:
        log_controller.set_default_level('info')
    if args.debug:
        log_controller.set_default_level('debug')
    asyncio.run(main(args))
