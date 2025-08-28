#!/usr/bin/env python
import asyncio
import argparse
import shutil
import json
from pathlib import Path
from dataclasses import asdict
from raftengine.api.deck_config import ClusterInitConfig, LocalConfig
from raftengine.deck.log_control import LogController
from raftengine_logs.sqlite_log import SqliteLog

from raft.raft_server import RaftServer, logger as raft_server_logger
from ops.direct import DirectCommander
from ops.raft_counters import RaftCounters
from ops.admin_common import ClusterServerConfig, get_cluster_config, get_server_status

def save_config(uri, working_dir, config, status):
    cluster_name = status['cluster_name']
    uris = list(config.nodes.keys())
    cdict = dict(node_uris=uris)
    cdict.update(asdict(config.settings))
    initial_config = ClusterInitConfig(**cdict)
    if "127.0.0.1" in str(uris):
        all_local = True
    else:
        all_local = False
    csc = ClusterServerConfig(uri, str(working_dir), cluster_name, initial_config, all_local=all_local)
    with open(Path(working_dir, 'server_config.json'), 'w') as f:
        f.write(json.dumps(asdict(csc), indent=2))
    return csc
    
async def joiner(base_dir, join_uri, cluster_uri):
    config = await get_cluster_config(cluster_uri)
    if join_uri in config.nodes:
        raise Exception(f"URI {join_uri} is already part of cluster")
    status = await get_server_status(cluster_uri)
    host,port = join_uri.split('/')[-1].split(':')
    wd = Path(base_dir, f"sum_raft_server.{host}.{port}")
    if not wd.exists():
        wd.mkdir(parents=True)
    csc = save_config(join_uri, wd, config, status)
    return csc, status['leader_uri']
    
async def starter(working_dir):
    if not working_dir.exists():
        raise Exception(f'specified working directory does not exist: {working_dir}')
    config_file_path = Path(working_dir, "server_config.json")
    if not config_file_path.exists():
        raise Exception(f'specified working directory does not contain server_config.json: {working_dir}')
    with open(config_file_path, 'r') as f:
        config_data = json.load(f)
        config = ClusterServerConfig.from_dict(config_data)
    return config
    
async def main(working_dir, join_uri=None, cluster_uri=None):
    
    if join_uri:
        config,leader_uri = await joiner(working_dir, join_uri, cluster_uri)
    else:
        config = await starter(working_dir)
    local_config = LocalConfig(uri=config.uri, working_dir=config.working_dir)
    server = RaftServer(RaftCounters, local_config, config.initial_config, config.cluster_name)
    direct = DirectCommander(server, raft_server_logger)
    server.set_direct_commander(direct)
    if join_uri:
        await server.start_and_join(leader_uri)
    else:
        await server.start()
    # now save up to date config
    config = await server.log.get_cluster_config()
    status = await server.direct_commander.get_status()
    save_config(server.uri, working_dir, config, status)
    try:
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
