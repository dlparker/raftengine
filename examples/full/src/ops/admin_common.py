#!/usr/bin/env python
import json
from collections import defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

from ops.direct import DirectCommandClient
from raft.raft_client import RaftClient
from raftengine.api.deck_config import ClusterInitConfig, LocalConfig
from raftengine.api.types import ClusterConfig, NodeRec, ClusterSettings


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
        
    

