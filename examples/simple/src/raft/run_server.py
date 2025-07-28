#!/usr/bin/env python
import asyncio
import argparse
from pathlib import Path
from raftengine.api.deck_config import ClusterInitConfig, LocalConfig
from raftengine.deck.log_control import LogController
log_controller = LogController.make_controller()
log_controller.set_default_level('debug')

import sys
src_dir = Path(__file__).parent.parent
sys.path.insert(0, str(src_dir))
from raft.raft_server import RaftServer


async def main(args):
    nodes = []
    for pnum in range(args.base_port, args.base_port + 3):
        nodes.append(f"aiozmq://127.0.0.1:{pnum}")

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

    work_dir = Path('/tmp', f"counters_raft_server.{args.index}")
    if args.clear_data:
        # already checked for --tell-me-twice above
        if work_dir.exists():
            shutil.rmtree(work_dir)
        work_dir.mkdir()
    elif not work_dir.exists():
        work_dir.mkdir()
    uri = nodes[args.index]
    local_config = LocalConfig(uri=uri, working_dir=work_dir)
    server = RaftServer(initial_cluster_config,
                        LocalConfig(uri=uri, working_dir=work_dir))
    await server.start()
    while not server.stopped:
        await asyncio.sleep(0.01)

if __name__=="__main__":
    
    parser = argparse.ArgumentParser(description='Counters Raft Server')

    parser.add_argument('-b', '--base_port', type=int, default=50050,
                        help='Port number for first node in cluster')
    parser.add_argument('-i', '--index', type=int, required=True,
                        help='Index of this server node in cluster node list')
    parser.add_argument('--clear-data', action='store_true',
                        help='Clear Raft log and bank db, must be used with --tell-me-twice')
    parser.add_argument('--tell-me-twice', action='store_true',
                        help='Really do the dangerous thing requested')

    # Parse arguments
    args = parser.parse_args()

    asyncio.run(main(args))
