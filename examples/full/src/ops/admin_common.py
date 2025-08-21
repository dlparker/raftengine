#!/usr/bin/env python
import asyncio
import argparse
import shutil
import json
import traceback
from pathlib import Path
from collections import defaultdict
from raftengine.api.deck_config import ClusterInitConfig, LocalConfig
from raftengine.api.types import ClusterConfig, NodeRec, ClusterSettings
from raftengine_logs.sqlite_log import SqliteLog
from raft.raft_client import RaftClient
from ops.direct import DirectCommandClient

import sys

async def find_local_clusters(root_working_dir):
    root = Path(root_working_dir)
    clusters = defaultdict(dict) # key is comma separated list of uris, sorted
    for wd in root.glob('counter_raft_server.*'):
        raft_log_file = Path(wd, "raftlog.db")
        config_file = Path(wd, "initial_config.json")
        uri_config_file = Path(wd, 'uri_config.txt')
        if not raft_log_file.exists() and not config_file.exists():
            print(f'{wd} looks like a server directory, but contains neither no raftlog.db or initial_config.json')
            continue
        saved_config = None
        if raft_log_file.exists():
            #print(f"checking log {raft_log_file}")
            try:
                log = SqliteLog(raft_log_file)
                await log.start()
                saved_config = await log.get_cluster_config()
                if saved_config is not None:
                    node_uris = list(saved_config.nodes.keys())
                    saved_uri = await log.get_uri()
                    node_uris.sort()
                    cluster_key = ",".join(node_uris)
                    rec = dict(uri=saved_uri, working_dir=str(wd))
                    clusters[cluster_key][saved_uri] = rec
                else:
                    print(f'{raft_log_file} contains no cluster config, must have never started')
            finally:
                try:
                    await log.stop()
                except:
                    pass
        if saved_config is None:
            if not config_file.exists() or not uri_config_file.exists():
                print(f'cannot reconstruct cluster configuration from {wd}')
            else:
                try:
                    with open(config_file, 'r') as f:
                        config_data = json.load(f)
                        initial_config = ClusterInitConfig(**config_data)
                except json.JSONDecodeError as e:
                    print(f"Error: Invalid JSON in '{config_file}': {e}")
                    sys.exit(1)
                with open(uri_config_file, 'r') as f:
                    uri = f.read().strip("\n")
                node_uris = list(initial_config.node_uris)
                node_uris.sort()
                cluster_key = ",".join(node_uris)
                rec = dict(uri=uri, working_dir=str(wd))
                clusters[cluster_key][uri] = rec
    return clusters
        
async def get_server_status(uri):
    client = DirectCommandClient(uri)
    status = None
    try:
        status = await client.get_status()
    except:
        pass
    await client.close()
    return status

async def get_log_stats(uri):
    client = DirectCommandClient(uri)
    log_stats = await client.log_stats()
    await client.close()
    return log_stats

async def get_cluster_config(uri):
    client = DirectCommandClient(uri)
    config = await client.get_cluster_config()
    await client.close()
    return config
        
async def take_snapshot(uri):
    client = DirectCommandClient(uri)
    snapshot = await client.take_snapshot()
    await client.close()
    return snapshot
        
async def stop_server(uri):
    client = DirectCommandClient(uri)
    status = await client.stop()
    await client.close()
    return status
        
async def server_exit_cluster(uri):
    client = DirectCommandClient(uri)
    status = await client.exit_cluster()
    await client.close()
    return status
        
async def send_heartbeats(uri):
    client = DirectCommandClient(uri)
    status = await client.send_heartbeats()
    await client.close()
    return status
        
