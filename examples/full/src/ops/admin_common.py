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
        
class ClusterBuilder:

    def __init__(self):
        pass

    def build_local(self, base_port=50100, slow_timeouts=False):
        for port in range(base_port, base_port + 3):
            uri = f"as_raft://127.0.0.1:{port}"
            self.node_uris.append(uri)
        
    
class ClusterOps:

    def __init__(self, static_config):
        self.config = cluster_config
        self.init_config = init_config
        if cluster_config is None and init_config is None:
            raise Exception(f'Both cluster_config and init_config cannot be none')
        self.clients = {}

    async def update_config(self):
        uri = self.get_uri_by_index(0)
        config = await self.direct_command(uri, 'get_config')
        self.config = config
        
    def uri_by_index(self, index):
        if self.config is not None:
            uris = list(self.config.nodes.keys())
        else:
            uris = self.init_config.node_uris:
        if index < 0 or index > len(uris):
            raise Exception(f"uri index {index} out of range")
        return uris[index]
        
    def get_client(self, uri):
        # don't check list, let caller give us any uri to try
        if node.uri not in self.clients:
            self.clients[uri] = RaftClient(uri, timeout=0.1)
        return self.clients[uri]
        
    def get_indexed_client(self, index=0):
        uri = self.get_uri_by_index(index)
        return self.get_client(uri)
        
    def get_server_uris(self):
        if self.config is not None:
            return list(self.config.nodes.keys())
        return self.init_config.node_uris

    async def direct_command(self, uri, command, *args):
        full_string = None
        if command not in RaftServer.direct_commands:
            raise Exception(f'command {command} unknown, should be in RaftServer.direct_commands'
                            ' {RaftServer.direct_commands}')
        if command == "set_logging_level":
            full_string = command
            for arg in args:
                full_string += f" {arg}"
        else:
            full_string = command
        client = self.get_client(uri)
        try:
            res = await client.direct_server_command(full_string)
        except Exception as e:
            raise Exception("Error: sending command to {uri} failed, may not be running")
        return res

    # NOT CONVERTED!
    async def stop_servers(self, uris=None):
        for index,server in self.servers.items():
            client = self.get_client(index)
            try:
                shut_res = await client.direct_server_command("stop")
                print(f"shutdown request for server {index} got {shut_res}")
            except Exception as e:
                print(f"shutdown request for server {index} got exception {e}")
            await client.close()
            if server['server'] is not None and False:
                await server['server_proc'].stop()

    async def check_server_ready(self, index, require_leader=True):
        server  =  self.servers[index]
        client = self.get_client(index)
        try:
            status = await client.direct_server_command("status")
        except Exception as e:
            return False
        if not require_leader:
            return  True
        if status['is_leader'] is False and status['leader_uri'] is None:
            return False

    async def elect_leader(self, index):
        running = await self.check_server_ready(index, require_leader=False)
        if not running:
            raise Exception(f'bad state, server {index} {self.servers[index]["uri"]} not running')
        client = self.get_client(index)
        await client.direct_server_command("take_power")
        start_time = time.time()
        time_limit = 0.5
        while time.time() - start_time < time_limit:
            status = await client.direct_server_command("status")
            if status['is_leader']:
                break
        if status['is_leader']:
            return
        raise Exception(f"server {index} {self.servers[index]['uri']} failed to win election in {time_limit}")

    async def find_leader(self):
        client = self.get_client(0)
        stats = await client.direct_server_command("status")
        return stats['leader_uri']
    
    async def check_cluster_ready(self):
        leader_index = None
        leader_spec = None
        status_recs = {}
        for index,server in self.servers.items():
            client = self.get_client(index)
            try:
                status = await client.direct_server_command("status")
            except Exception as e:
                return False, f"Server {index} {server['uri']} raised exception {e}"
            if not isinstance(status, dict):
                import ipdb; ipdb.set_trace()
            status_recs[index] = status
            if status['is_leader']:
                leader_index = index
                leader_spec = server
        if leader_index is None:
            return False, f"No server reports that it is leader, probably need to issue take_power command"
        for index,status in status_recs.items():
            if status['leader_uri'] != leader_spec['uri']:
                return False, f"Server {index} {status['uri']} says leader is {status['leader_uri']} but leader is" \
                    f" {leader_spec['uri']}"
        return True, f"leader is {leader_spec['uri']}"
            
    async def prepare_new_node(self):
        index = len(self.node_uris) + 1
        port = self.base_port + index
        uri = f"as_raft://127.0.0.1:{port}"
        leader_uri = await self.find_leader()
        work_dir = Path('/tmp', f"simple_raft_server.{index}")
        if not work_dir.exists():
            work_dir.mkdir()
            
        spec = {
            'uri': uri,
            'initial_cluster_config': self.initial_cluster_config,
            'local_config': LocalConfig(uri=uri, working_dir=work_dir),
            'server': None,
            'server_proc': None,
            'client': None
        }
