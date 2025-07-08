#!/usr/bin/env python
import asyncio
import argparse
import sys
from pathlib import Path
from operator import methodcaller
from raftengine.api.deck_config import ClusterInitConfig, LocalConfig
top_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(top_dir))
from src.raft.raft_components.server_main import server_main

nodes = ["grpc://localhost:50055",
         "grpc://localhost:50056",
         "grpc://localhost:50057",]

async def main():
    parser = argparse.ArgumentParser(description='Raft Banking Server starter')
    parser.add_argument('--index', '-1', 
                        type=int, default=0,
                        help=f'Server index in list {nodes} (default: 0)')
    args = parser.parse_args()
    c_config = ClusterInitConfig(node_uris=nodes,
                                 heartbeat_period=10000,
                                 election_timeout_min=20000,
                                 election_timeout_max=20001,
                                 use_pre_vote=False,
                                 use_check_quorum=True,
                                 max_entries_per_message=10,
                                 use_dynamic_config=False)
    uri = nodes[args.index]
    work_dir = Path('/tmp', f"rserver_{args.index}")
    if not work_dir.exists():
        work_dir.mkdir()
    local_config = LocalConfig(uri=uri, working_dir=work_dir)
    await server_main(uri, c_config,  local_config)
    
if __name__ == "__main__":
    asyncio.run(main())
