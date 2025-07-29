#!/usr/bin/env python
import asyncio
import shutil
from pathlib import Path
from subprocess import Popen
from raftengine.api.deck_config import ClusterInitConfig, LocalConfig
from rpc.run_tools import RunTools as RPCRunTools
from raft.raft_server import RaftServer
from raft.raft_client import RaftClient

class Cluster:

    def __init__(self, transport, base_port=59050):
        self.transport = transport
        self.base_port = base_port
        self.rpc_tools = RPCRunTools(transport)
        self.node_uris = []
        self.servers = {}
        for port in range(base_port, base_port + 3):
            uri = f"{transport}://localhost:{port}"
            self.node_uris.append(uri)
            
        heartbeat_period=10000
        election_timeout_min=20000
        election_timeout_max=20001
        self.initial_cluster_config = ClusterInitConfig(node_uris=self.node_uris,
                                                        heartbeat_period=heartbeat_period,
                                                        election_timeout_min=election_timeout_min,
                                                        election_timeout_max=election_timeout_max,
                                                        use_pre_vote=False,
                                                        use_check_quorum=True,
                                                        max_entries_per_message=10,
                                                        use_dynamic_config=False)
        for index,uri in enumerate(self.node_uris):
            work_dir = Path('/tmp', f"counters_raft_server.{self.transport}.{index}")
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

    def clear_server_files(self):
        for index, spec in self.servers.items():
            work_dir = Path(spec['local_config'].working_dir)
            if work_dir.exists():
                shutil.rmtree(work_dir)
            work_dir.mkdir()
            
    def get_client(self, index=0):
        if index in self.servers:
            spec = self.servers[index]
            if spec['client'] is not None:
                return spec['client']
        uri = self.node_uris[index]
        client = RaftClient(uri, self.rpc_tools.get_client_class(), timeout=0.1)
        if index in self.servers:
            spec['client'] = client
        return client
    
    async def start_servers(self, targets=None, in_process=False, start_paused=False):
        for index,spec in self.servers.items():
            if targets and spec['uri'] not in targets:
                continue
            if in_process:
                server = RaftServer(spec['initial_cluster_config'], spec['local_config'],
                                    self.rpc_tool.get_server_class(), self.rpc_tool.get_client_class(),
                                    start_paused)
                await server.start()
                spec['server'] = server
            else:
                this_dir = Path(__file__).parent
                sfile = Path(this_dir, 'run_server.py')
                cmd = [str(sfile), "-b",  f"{self.base_port}", "-i",  f"{index}", '-t', self.transport]
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
            shut_res = await client.direct_server_command("stop")
            print(f"shutdown request for server {index} got {shut_res}")
            await client.close()
            if server['server'] is not None and False:
                await server['server_proc'].stop()
                
    async def direct_command(self, uri, command, *args):
        full_string = None
        if command in ["ping", "getpid", "stop", "take_power",
                       "start_raft", "stop_raft", "status", "get_logging_dict"]:
            full_string = command
        elif command == "set_logging_level":
            full_string = command
            for arg in args:
                full_string += " {arg}"
        else:
            raise Exception(f'command {command} unknown')
        for index,spec in self.servers.items():
            if spec['uri'] == uri:
                client = self.get_client(index)
                res = await client.direct_server_command(full_string)
                return res
        raise Exception(f'could not find server with uri {uri}')
