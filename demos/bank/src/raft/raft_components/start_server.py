#!/usr/bin/env python
import asyncio
import argparse
import sys
from pathlib import Path
from operator import methodcaller
from raftengine.api.deck_config import ClusterInitConfig, LocalConfig
top_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(top_dir))
from src.raft.raft_components.pilot import DeckHand
from src.raft.raft_components.sqlite_log import SqliteLog
from src.raft.raft_components.server import RaftServer
from src.raft_prep.transports.grpc.client import get_grpc_client

nodes = ["grpc://localhost:50055",
         "grpc://localhost:50056",
         "grpc://localhost:50057",]

async def main():
    parser = argparse.ArgumentParser(description='Raft Banking Server starter')
    parser.add_argument('--index', '-1', 
                        type=int, default=0,
                        help=f'Server index in list {nodes} (default: 0)')
    args = parser.parse_args()
    uri = nodes[args.index]
    c_config = ClusterInitConfig(node_uris=nodes,
                                 heartbeat_period=10000,
                                 election_timeout_min=20000,
                                 election_timeout_max=20001,
                                 use_pre_vote=False,
                                 use_check_quorum=True,
                                 max_entries_per_message=10,
                                 use_dynamic_config=False)
    local_config = LocalConfig(uri=uri, working_dir='/tmp/')
    tmp = uri.split("/")  # Fixed: was 'url', now 'uri'
    if tmp[0].strip(':') != "grpc":
        raise Exception(f'Misconfigure, should be grpc, not {tmp[0]}')
    number = tmp[-1].split(':')[-1]
    path = Path('/tmp', f"rserver_{number}.db")
    print(path)
    log = SqliteLog(path)
    log.start()
    await log.get_last_index()
    server = Server()
    def client_maker(target_uri):
        tmp = target_uri.split("/")  # Fixed: was 'url', now 'target_uri'
        if tmp[0].strip(':') != "grpc":
            raise Exception(f'Misconfigure, should be grpc, not {tmp[0]}')
        host, port = tmp[-1].split(":")
        return get_grpc_client(host, int(port))
    
    deckhand = DeckHand(server, log, client_maker, c_config, local_config)
    server.set_deckhand(deckhand)
    await deckhand.start()
    print(f"{uri} deck started", flush=True)
    while not deckhand.deck.stopped:
        await asyncio.sleep(0.0001)
    
if __name__ == "__main__":
    asyncio.run(main())
