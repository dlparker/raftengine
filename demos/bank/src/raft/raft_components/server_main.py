#!/usr/bin/env python
import asyncio
import argparse
import sys
from pathlib import Path
import logging
from raftengine.deck.log_control import LogController
top_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(top_dir))
from src.raft.raft_components.pilot import DeckHand
from src.raft.raft_components.sqlite_log import SqliteLog
from src.raft.raft_components.raft_server import RaftServer
from src.raft_prep.transports.grpc.client import get_grpc_client

my_loggers = [('bank_demo', 'Demo raft integration banking app'),]
log_control = LogController(my_loggers, default_level="info")
logger = logging.getLogger('bank_demo')

async def server_main(uri, cluster_config, local_config):
    path_root = Path(local_config.working_dir)
    if not path_root.exists():
        path_root.mkdir()
    db_path = Path(path_root, 'raft_log.db')
    log = SqliteLog(db_path)
    log.start()
    await log.get_last_index()
    tmp = uri.split("/")  # Fixed: was 'url', now 'target_uri'
    transport = tmp[0].strip(':')
    if transport == "grpc":
        def client_maker(target_uri):
            tmp = target_uri.split("/")  # Fixed: was 'url', now 'target_uri'
            if tmp[0].strip(':') != "grpc":
                raise Exception(f'Misconfigure, should be grpc, not {tmp[0]}')
            host, port = tmp[-1].split(":")
            return get_grpc_client(host, int(port))
    else:
        raise Exception(f'no code for transport {transport}')
    
    server = RaftServer()
    deckhand = DeckHand(server, log, client_maker, cluster_config, local_config)
    server.set_deckhand(deckhand)
    await deckhand.start()
    logger.info(f"{uri} deck started")
    while not deckhand.deck.stopped:
        await asyncio.sleep(0.0001)
    
