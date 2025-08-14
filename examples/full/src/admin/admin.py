#!/usr/bin/env python
import asyncio
import shutil
from pathlib import Path
import time
from subprocess import Popen
from raftengine.api.deck_config import ClusterInitConfig, LocalConfig
from raft.raft_server import RaftServer
from raft.raft_client import RaftClient

class Cluster:

    def __init__(self, cluster_config, init_config=None):
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
        
