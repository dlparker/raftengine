#!/usr/bin/env python
import asyncio
import argparse
import shutil
import json
import traceback
from pathlib import Path
from dataclasses import dataclass, asdict
from collections import defaultdict
from typing import Optional
from raftengine.api.deck_config import ClusterInitConfig, LocalConfig
from raftengine.api.types import ClusterConfig, NodeRec, ClusterSettings
from raftengine_logs.sqlite_log import SqliteLog
from raft.raft_client import RaftClient
from ops.direct import DirectCommandClient

import sys

@dataclass
class ClusterServerConfig:
    uri: str
    working_dir:str
    cluster_name: str
    initial_config: ClusterInitConfig
    last_config: Optional[ClusterConfig] = None
    all_local: Optional[bool] = False

    @classmethod
    def from_dict(cls, data):
        initial_config = ClusterInitConfig(**data['initial_config'])
        res = cls(data['uri'], data['working_dir'], data['cluster_name'], initial_config, all_local=data['all_local'])
        if data['last_config'] is not None:
            cdata = data['last_config'] 
            settings = ClusterSettings(**cdata['settings'])
            nodes = []
            for subd in cdata['nodes']:
                nodes.append(NodeRec(**subd))
            res.last_config = ClusterConfig(nodes=nodes, settings=settings)
        return res

class ClusterBuilder:

    def __init__(self):
        pass

    def build_common(self, name, node_uris, slow_timeouts=False, all_local=False):
        if slow_timeouts:
            heartbeat_period=10000
            election_timeout_min=10000
            election_timeout_max=10000
        else:
            heartbeat_period=0.01
            election_timeout_min=0.25
            election_timeout_max=0.35
        initial_config = ClusterInitConfig(node_uris=node_uris,
                                           heartbeat_period=heartbeat_period,
                                           election_timeout_min=election_timeout_min,
                                           election_timeout_max=election_timeout_max,
                                           use_pre_vote=False,
                                           use_check_quorum=True,
                                           max_entries_per_message=10,
                                           use_dynamic_config=False)
        server_configs = []
        for uri in node_uris:
            host,port = uri.split('/')[-1].split(':')
            work_dir = Path("/tmp", f"full_raft_server.{host}.{port}")
            server_configs.append(ClusterServerConfig(uri, str(work_dir), name,initial_config, all_local=all_local))
        return server_configs
        
    def build_local(self, name='local', base_port=50100, slow_timeouts=False):
        node_uris = []
        for port in range(base_port, base_port + 3):
            uri = f"full://127.0.0.1:{port}"
            node_uris.append(uri)
        return self.build_common(name, node_uris, slow_timeouts, all_local=True)

    def build(self, name, hosts, base_port=50090, slow_timeouts=False):
        if len(hosts) < 3:
            Exception("At least three host names must be provided so three nodes can be configured. Host name can be repeated")
        node_uris = []
        used_hosts = set()
        for host in hosts:
            port = base_port
            if host in ("127.0.0.1", "localhost"):
                raise Exception("Can't use loopback address in real host list")
            uri = f"full://{host}:{port}"
            while uri in node_uris:
                port += 1
                uri = f"full://{host}:{port}"
            node_uris.append(uri)
        return self.build_common(name, node_uris, slow_timeouts)

    def setup_local_files(self, server_configs, root_dir, local_host_names=None, overwrite=False):
        for s_config in server_configs:
            if not s_config.all_local:
                host,port = s_config.uri.split('/')[-1].split(':')
                if host not in local_host_names:
                    continue
            wd = Path(s_config.working_dir)
            if not wd.exists():
                wd.mkdir(parents=True)
            config_file_path = Path(wd, "server_config.json")
            if config_file_path.exists() and not overwrite:
                raise Exception(f"Without overwrite, refusing to overwrite {config_file_path}")
            with open(config_file_path, 'w') as f:
                f.write(json.dumps(asdict(s_config), indent=2))
            db_file_path = Path(wd, "raftlog.db")
            if db_file_path.exists():
                if not overwrite:
                    raise Exception(f"Without overwrite, refusing to overwrite {db_file_path}")
                db_file_path.unlink()
            
class ClusterFinder:

    def __init__(self, root_dir=None, uri=None):
        self.root_dir = root_dir
        self.uri = uri
        self.clusters = {}

    async def discover(self):
        if self.root_dir is None and self.uri is None:
            raise Exception('cannot discover cluster unless either config file parent dir or uri is provided')
        if self.uri:
            name, servers = await self.query_discover(self.uri)
            self.clusters[name] = servers
        else:
            clusters = await self.file_discover(self.root_dir)
            for name, servers in clusters.items():
                self.clusters[name] = servers
        return self.clusters
    
    async def file_discover(self, root_working_dir):
        root = Path(root_working_dir)
        clusters = defaultdict(dict)
        for wd in root.glob('full_raft_server.*'):
            config_file_path = Path(wd, "server_config.json")
            if not config_file_path.exists():
                continue
            with open(config_file_path, 'r') as f:
                config_data = json.load(f)
                config = ClusterServerConfig.from_dict(config_data)
            if config.cluster_name is None:
                print(f"Cannot save cluster data for null cluster name from {config_file_path} \n{json.dumps(asdict(config))}")
                continue
            index = len(clusters[config.cluster_name])
            clusters[config.cluster_name][index] = config
        for cname, cluster in clusters.items():
            item_list = []
            for index, config in cluster.items():
                item_list.append(config)
            slist = sorted(item_list, key=lambda x:x.uri)
            cluster = {}
            for index,item in enumerate(slist):
                cluster[str(index)] = item
            clusters[cname] = cluster
            
        return clusters

    async def query_discover(self, query_uri):
        config = await get_cluster_config(query_uri)
        status = await get_server_status(query_uri)
        cluster_name = status['cluster_name']
        uris = list(config.nodes.keys())
        uris.sort()
        if "127.0.0.1" in query_uri:
            all_local = True
        else:
            all_local = False
        servers = {}
        for index,uri in enumerate(uris):
            # try getting the status from the server to get the working directory, or set it to None
            i_status = await get_server_status(uri)
            if i_status:
                wd = i_status['working_dir']
            else:
                wd = None
            cdict = dict(node_uris=uris)
            cdict.update(asdict(config.settings))
            initial_config = ClusterInitConfig(**cdict)
            csc = ClusterServerConfig(uri, wd, cluster_name, initial_config, all_local=all_local)
            servers[str(index)] = csc
        return cluster_name, servers

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
            uris = self.init_config.node_uris
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
        uri = f"full://127.0.0.1:{port}"
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

    
