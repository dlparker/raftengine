#!/usr/bin/env python
import asyncio
import shutil
from pathlib import Path
import time
from subprocess import Popen
from raftengine.api.deck_config import ClusterInitConfig, LocalConfig
from raft.raft_server import RaftServer
from raft.raft_client import RaftClient
from raft.direct import DirectCommander

class Cluster:

    def __init__(self, base_port=59050):
        self.base_port = base_port
        self.node_uris = []
        self.servers = {}
        for port in range(base_port, base_port + 3):
            uri = f"full://127.0.0.1:{port}"
            self.node_uris.append(uri)
            
        heartbeat_period=0.01
        election_timeout_min=0.25
        election_timeout_max=0.35
        self.initial_cluster_config = ClusterInitConfig(node_uris=self.node_uris,
                                                        heartbeat_period=heartbeat_period,
                                                        election_timeout_min=election_timeout_min,
                                                        election_timeout_max=election_timeout_max,
                                                        use_pre_vote=False,
                                                        use_check_quorum=True,
                                                        max_entries_per_message=10,
                                                        use_dynamic_config=False)
        for index,uri in enumerate(self.node_uris):
            work_dir = Path('/tmp', f"simple_raft_server.{index}")
            if not work_dir.exists():
                work_dir.mkdir()
            
            self.servers[index] = {
                'uri': uri,
                'initial_cluster_config': self.initial_cluster_config,
                'local_config': LocalConfig(uri=uri, working_dir=work_dir),
                'server': None,
                'server_proc': None,
                'client': None
            }

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
        
        
    def clear_server_files(self):
        for index, spec in self.servers.items():
            work_dir = Path(spec['local_config'].working_dir)
            if work_dir.exists():
                print(f"removing {work_dir}")
                shutil.rmtree(work_dir)
            work_dir.mkdir()
            
    def get_client(self, index=0):
        if index in self.servers:
            spec = self.servers[index]
            if spec['client'] is not None:
                return spec['client']
        uri = self.node_uris[index]
        client = RaftClient(uri,timeout=0.1)
        if index in self.servers:
            spec['client'] = client
        return client
    
    def get_server_props(self, index=0):
        return self.servers[index]
    
    async def start_servers(self, targets=None, default_logging_level='error'):
        for index,spec in self.servers.items():
            if targets and spec['uri'] not in targets:
                continue
            this_dir = Path(__file__).parent
            sfile = Path(this_dir, 'run_server.py')
            cmd = [str(sfile), "-b",  f"{self.base_port}", "-i",  f"{index}"]
            if default_logging_level == "error":
                cmd.append("-E")
            elif default_logging_level == "warning":
                cmd.append("-W")
            elif default_logging_level == "info":
                cmd.append("-I")
            elif default_logging_level == "debug":
                cmd.append("-D")
            else:
                raise Exception(f'invalid default logging level "{default_logging_level}"')
            work_dir = spec['local_config'].working_dir
            stdout_file = Path(work_dir,'server.stdout')
            stderr_file = Path(work_dir,'server.stderr')
            with open(stdout_file, 'w') as stdout_f, open(stderr_file, 'w') as stderr_f:
                process = Popen(cmd, stdout=stdout_f,stderr=stderr_f, start_new_session=True)
            # Wait a moment to see if process starts successfully
            await asyncio.sleep(0.1)
            if process.poll() is None:  # Process is still running
                if False:
                    print(f"Server {index} started successfully")
                    print(f"  stdout: {stdout_file}")
                    print(f"  stderr: {stderr_file}")
                    spec['server_proc'] = process
            else:
                print(f"Server {index} failed to start")
                # Read the error logs
                if stderr_file.exists():
                    with open(stderr_file, 'r') as f:
                        stderr_content = f.read()
                        if stderr_content:
                            print(f"stderr: {stderr_content}")
                raise Exception(f"Server {index} failed to start")
                
    async def stop_servers(self):
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
            
    async def direct_command(self, uri, command, *args):
        full_string = None
        if command not in DirectCommander.direct_commands:
            raise Exception(f'command {command} unknown, should be in RaftServer.direct_commands'
                            ' {RaftServer.direct_commands}')
        if command == "set_logging_level":
            full_string = command
            for arg in args:
                full_string += f" {arg}"
        else:
            full_string = command
        for index,spec in self.servers.items():
            if spec['uri'] == uri:
                client = self.get_client(index)
                try:
                    res = await client.direct_server_command(full_string)
                except Exception as e:
                    raise Exception("Error: sending command to {uri} failed, may not be running")
                return res
        raise Exception(f'could not find server with uri {uri}')
