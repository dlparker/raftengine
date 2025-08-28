#!/usr/bin/env python
import sys
import asyncio
import json
import argparse
import shutil
import time
import traceback
from pathlib import Path
from aiocmd import aiocmd
from subprocess import Popen
from pprint import pprint
from collections import defaultdict
from dataclasses import asdict
src_dir = Path(__file__).parent.parent
sys.path.insert(0, str(src_dir))

from ops.admin_common import (get_server_status, get_log_stats, send_heartbeats,
                              get_cluster_config, stop_server, take_snapshot, server_exit_cluster)
from ops.admin_common import ClusterBuilder, ClusterFinder


class ClusterMgr:

    def __init__(self):
        self.clusters = {}
        self.status_records = {}
        self.selected = None
        self.json_indent = 4

    async def get_status(self, cluster_name=None):
        if cluster_name is None:
            if self.selected is None:
                raise Exception('no cluster name provided and no cluster selected')
            cluster_name = self.selected
        # this is a good time to look for servers that have been removed
        # from the or added to the cluster, so lets just update everything
        # if we can talk to a server
        config_check = None
        cluster = self.clusters[cluster_name]
        for index, s_config in cluster.items():
            status = await get_server_status(s_config.uri)
            if status is not None:
                config_check = s_config
                break
        if config_check is not None:
            try:
                q_finder = ClusterFinder(uri=config_check.uri)
                clusters = await q_finder.discover()
                cluster_data = clusters[cluster_name]
                for n_index, n_server in cluster_data.items():
                    if n_index not in cluster:
                        # server must have been added since last check
                        cluster[n_index] = n_server
                for c_index, c_server in cluster.items():
                    if c_index not in cluster_data:
                        # server must have been deleted since last check
                        del cluster[c_index]
            except Exception as e:
                #traceback.print_exc()
                #print(e)
                pass

        self.status_records[cluster_name] = stat_dict = {}
        cluster = self.clusters[cluster_name] 
        for index, s_config in cluster.items():
            status = await get_server_status(s_config.uri)
            stat_dict[index] = status
        return stat_dict
        return None

    async def query_discover(self, port, host='127.0.0.1', select=True):
        target_uri = f"sum://{host}:{port}"
        q_finder = ClusterFinder(uri=target_uri)
        try:
            clusters = await q_finder.discover()
        except:
            raise Exception(f"Not able to discover cluster at {target_uri}, is it running?")
        cluster_name = next(iter(clusters))
        cluster_data = clusters[cluster_name]
        # Add to internal clusters list
        self.clusters[cluster_name] = cluster_data
        self.selected = cluster_name
        return cluster_name

    async def discover_cluster_files(self, search_dir="/tmp", return_json=False):
        f_finder = ClusterFinder(root_dir=search_dir)
        clusters = await f_finder.discover()
        if len(clusters) > 0:
            self.clusters.update(clusters)
        selected_cluster = None
        if len(self.clusters) == 1:
            cluster_name = next(iter(self.clusters))
            self.selected = cluster_name
            selected_cluster = cluster_name
        result = {
            "search_directory": str(search_dir),
            "query_uri": None,
            "clusters": clusters,
            "selected_cluster": selected_cluster,
        }
        return self.response_or_json(result, return_json)
    
    def response_or_json(self, data, return_json=False):
        """Utility method to format response data as JSON string if requested"""
        if return_json:
            if data is None:
                return ""
            return json.dumps(data, indent=self.json_indent, default=lambda o:o.__dict__)
        return data
    
    def require_selection(self):
        """Enhanced helper to validate cluster selection, returns structured data"""
        if len(self.clusters) == 0:
            raise Exception("No clusters found, try find_clusters or add_cluster")
        if not self.selected:
            raise Exception("Must select a cluster first")
        return self.clusters[self.selected]
    
    async def require_server_at_index(self, index:str):
        """Enhanced helper to validate server index, returns structured data"""
        cluster = self.require_selection()
        
        if index not in cluster:
            raise Exception(f"Requested server number {index} not found, valid values are {list(cluster.keys())}")
        
        server = cluster[index]
        status_dict = await self.get_status() 
        status = status_dict[index]
        return cluster, server, status

    async def select_cluster(self, cluster_name):
        if cluster_name not in self.clusters:
            raise Exception(f"cannot select non-existent cluster {cluster_name}")
        self.selected = cluster_name
        await self.get_status()
        
    async def add_cluster(self, port, host='127.0.0.1', return_json=False):
        cluster_name = await self.query_discover(port, host, True)
        clusters_dict = await self.list_clusters(return_json=False)
        target_uri = f"sum://{host}:{port}"
        result = {
            "search_directory": None,
            "query_uri": target_uri,
            "clusters": clusters_dict,
            "selected_cluster": cluster_name,
        }
        return self.response_or_json(result, return_json)
        
    async def list_clusters(self, return_json=False):
        if len(self.clusters) == 0:
            return self.response_or_json({}, return_json)
        
        clusters_data = {}
        for name, cluster in self.clusters.items():
            await self.get_status(name)
            running = False
            servers_data = {}
            
            for index, s_config in cluster.items():
                record = self.status_records[name][index]
                servers_data[index] = s_config
            clusters_data[name] = servers_data
        return self.response_or_json(clusters_data, return_json)

    async def server_status(self, index:str, return_json=False):
        cluster, server, status = await self.require_server_at_index(index)
        # get an up to date status
        status_dict = await self.get_status(self.selected)
        return self.response_or_json(status_dict[index], return_json)

    async def cluster_status(self, name=None, return_json=False):
        if len(self.clusters) == 0:
            raise Exception("No clusters cataloged")
        if not self.selected and name is None:
            raise Exception("No cluster name provided and no cluster selected")
        if name is None:
            name = self.selected
        if name not in self.clusters:
            raise Exception(f"Cluster catalog does not contain {cluster_name}")
        cluster = self.clusters[name]
        status_dict = await self.get_status(name)
        servers_data = {}
        
        for index, s_config in cluster.items():
            status = status_dict[index]
            servers_data[index] = {
                "config": s_config,
                "status": status
            }
        result = servers_data
        return self.response_or_json(result, return_json)

    async def stop_server(self, index:str, return_json=False):
        """Logic for stopping indexed server"""
        cluster, server, status = await self.require_server_at_index(index)
        was_running = status is not None
        if was_running:
            await stop_server(server.uri)
        result = dict(config=server, was_running=was_running)
        return self.response_or_json(result, return_json)

    async def log_stats(self, index:str, return_json=False):
        cluster, server, status = await self.require_server_at_index(index)
        if not status:
            raise Exception(f"Server {server.uri} is not running, can't get log_stats")
        log_stats = await get_log_stats(server.uri)
        return self.response_or_json(log_stats, return_json)

    async def start_servers(self, hostnames=['127.0.0.1',], wait_for_status=True, return_json=False):
        cluster = self.require_selection()
        
        local_servers = {}
        for index, server in cluster.items():
            host = server.uri.split('/')[-1].split(':')[0]
            if host in hostnames:
                local_servers[server.uri] = server

        initial_status = await self.cluster_status(return_json=False)
        if len(local_servers) == 0:
            raise Exception(f"Cluster {self.selected} has no servers on any host in list {hostnames}")

        procs = {}
        for uri, server in local_servers.items():
            status = await get_server_status(uri)
            if status is None:
                this_dir = Path(__file__).parent
                working_dir = server.working_dir
                sfile = Path(this_dir, 'run_server.py')
                cmd = [str(sfile), "-w", working_dir]
                stdout_file = Path(working_dir, 'server.stdout')
                stderr_file = Path(working_dir, 'server.stderr')

                with open(stdout_file, 'w') as stdout_f, open(stderr_file, 'w') as stderr_f:
                    process = Popen(cmd, stdout=stdout_f, stderr=stderr_f, start_new_session=True)
                    procs[uri] = dict(stderr_file=stderr_file, stdout_file=stdout_file, process=process)
        

        await asyncio.sleep(0.01)
        for uri, spec in procs.items():
            process = spec['process']
            if process.poll() is not None:
                extra = ""
                stdout_file = spec['stdout_file']
                if stdout_file.exists():
                    with open(stdout_file, 'r') as f:
                        stdout_content = f.read()
                    extra += f"\n--- stdout ---\n{stdout_content}"
                stderr_file = spec['stderr_file']
                if stderr_file.exists():
                    with open(stderr_file, 'r') as f:
                        stderr_content = f.read()
                    extra += f"\n--- stderr ---\n{stderr_content}"
                    
                raise Exception(f"process for uri {uri} failed to start {extra}")

        async def check_all_running():
            status_dict = await self.get_status()
            for index, status in status_dict.items():
                if status is None:
                    return False
            return True
        if wait_for_status:
            start_time = time.time()
            while not await check_all_running() and time.time() - start_time  < 3:
                await asyncio.sleep(0.01)
            if not await check_all_running():
                raise Exception('Servers did not reply to status checks within 3 seconds')
        final_status = await self.cluster_status(return_json=False)
        
        result = {
            "local_hostnames": hostnames,
            "local_servers_found": local_servers,
            "initial_cluster_status": initial_status,
            "final_cluster_status": final_status,
        }
        return self.response_or_json(result, return_json)

    async def get_server_config(self, index, return_json=False):
        cluster, server, status = await self.require_server_at_index(index)
        return server
        
    async def get_local_server_configs(self, local_host_names, return_json=False):
        cluster = self.require_selection()
        servers  = {}
        for index, config in cluster.items():
            host = config.uri.split('/')[-1].split(':')[0]
            if host in local_host_names:
                servers[index] = config
        return servers
        
    async def stop_cluster(self, return_json=False):
        cluster = self.require_selection()

        server_recs = {}
        for index, server in cluster.items():
            status = await get_server_status(server.uri)
            was_running = status is not None
            if was_running:
                await stop_server(server.uri)
            server_recs[index] = dict(config=server, was_running=was_running)
        result = {
            "cluster_name": self.selected,
            "server_records": server_recs,
        }
        return self.response_or_json(result, return_json)
    
    async def update_cluster(self, name=None, return_json=False):
        if len(self.clusters) == 0:
            raise Exception("No clusters cataloged")
        if not self.selected and name is None:
            raise Exception("No cluster name provided and no cluster selected")
        if name is None:
            name = self.selected
        if name not in self.clusters:
            raise Exception(f"Cluster catalog does not contain {cluster_name}")
        await self.get_status(name)
        return await self.cluster_status(name=name, return_json=return_json)

    async def create_cluster(self, cluster_name, local_servers_directory, hosts, local_host_names,
                             base_port=30000, return_json=False):
        f_finder = ClusterFinder(root_dir=local_servers_directory)
        clusters = await f_finder.discover()
        removed = False
        if cluster_name in clusters:
            raise Exception(f"cannot create cluster {cluster_name}, it already exists locally in {local_servers_directory}")

        cb = ClusterBuilder()
        all_servers = cb.build(cluster_name, hosts=hosts, base_port=base_port, base_dir=local_servers_directory)
        cb.setup_local_files(all_servers, local_servers_directory, local_host_names=local_host_names)

        # Update status
        local_servers = []
        server_dict = {}
        for index, server in enumerate(all_servers):
            idx_str = str(index)
            server_dict[idx_str] = server
            host = server.uri.split('/')[-1].split(':')[0]
            if host in local_host_names:
                local_servers.append(server)

        self.clusters[cluster_name] = server_dict
        self.selected = cluster_name

        result = {
            "cluster_name": cluster_name,
            "local_servers_directory": str(local_servers_directory),
            "base_port": base_port,
            "local_servers": local_servers,
            "selected": True,
        }
        return self.response_or_json(result, return_json)
        
    async def create_local_cluster(self, cluster_name, directory="/tmp", force=False, return_json=False):
        # Check if cluster already exists
        f_finder = ClusterFinder(root_dir=directory)
        clusters = await f_finder.discover()
        removed = False
        if cluster_name in clusters:
            if not force:
                raise Exception(f"cannot create local cluster {cluster_name}, it already exists. Did you forget force=True?")
            removed = True
            cluster = clusters[cluster_name]
            for index, server in cluster.items():
                status = await get_server_status(server.uri)
                if status:
                    await stop_server(server.uri)
                wd = Path(server.working_dir)
                shutil.rmtree(wd)
            
        # Find available port
        avail_port = None
        try_port = 50100
        while True:
            bad_pass = False
            for name, servers in clusters.items():
                for index, server in servers.items():
                    host, port = server.uri.split("/")[-1].split(':')
                    if port == str(try_port):
                        try_port += 100
                        bad_pass = True
                        break
                if bad_pass:
                    break
            if not bad_pass:
                avail_port = try_port
                break

        # Build local cluster
        cb = ClusterBuilder()
        local_servers = cb.build_local(name=cluster_name, base_port=avail_port, base_dir=str(directory))
        cb.setup_local_files(local_servers, directory, overwrite=force)

        # Convert to server dictionary
        server_dict = {}
        servers_created = {}
        for index, server in enumerate(local_servers):
            idx_str = str(index)
            server_dict[idx_str] = server
            servers_created[idx_str] = dict(uri=server.uri, working_dir=server.working_dir)

        # Add to clusters and select
        self.clusters[cluster_name] = server_dict
        self.selected = cluster_name
        await self.get_status(cluster_name=cluster_name)
        result = {
            "cluster_name": cluster_name,
            "directory": str(directory),
            "force": force,
            "success": True,
            "base_port": avail_port,
            "servers_created": servers_created,
            "selected": True,
            "force_removed": removed,
            "error": None
        }
        return self.response_or_json(result, return_json)

    async def send_heartbeats(self, return_json=False):
        cluster = self.require_selection()
        status = None
        for index, server in cluster.items():
            status = await get_server_status(server.uri)
            if status:
                break
            
        if status is None:
            raise Exception(f"Cannot send heartbeat in cluster {self.selected}, no servers are running")
        leader = status['leader_uri']
        if leader is None:
            raise Exception(f"Cannot send heartbeat in cluster {self.selected}, no leader has been elected")
        await send_heartbeats(leader)
        result = {
            "cluster_name": self.selected,
            "leader_uri": leader,
        }
        return self.response_or_json(result, return_json)
    
    async def take_snapshot(self, index:str, return_json=False):
        cluster, server, status = await self.require_server_at_index(index)
        pre_status = await get_server_status(server.uri)
        snapshot = await take_snapshot(server.uri)
        post_status = await get_server_status(server.uri)
            
        result = {
                "server_index": str(index),
                "server_uri": server.uri,
                "pre_snapshot_status": pre_status,
                "snapshot": snapshot,
                "post_snapshot_status": post_status,
        }
        return self.response_or_json(result, return_json)

    async def new_server(self, hostname='127.0.0.1',  return_json=False):
        cluster = self.require_selection()
        status = None
        max_port = 0
        for index, server in cluster.items():
            port = int(server.uri.split(':')[-1])
            max_port = max(max_port, port)
            s = await get_server_status(server.uri)
            if s:
                status = s
        new_port = max_port + 1
        if status is None:
            raise Exception(f"Cannot add a server to cluster {self.selected}, no servers are running")
        leader = status['leader_uri']
        if leader is None:
            raise Exception(f"Cannot add a server to cluster {self.selected}, no leader has been elected")
        # find the base working directory from the status
        base_dir = Path(status['working_dir']).parent
        this_dir = Path(__file__).parent
        new_uri = f"sum://{hostname}:{new_port}"
        sfile = Path(this_dir, 'run_server.py')
        cmd = [str(sfile), "-b", str(base_dir), '--join_uri', new_uri, '--cluster_uri', leader]
        working_dir = Path(base_dir, f"sum_raft_server.{hostname}.{new_port}")
        if not working_dir.exists():
            working_dir.mkdir(parents=True)
        stdout_file = Path(working_dir, 'server.stdout')
        stderr_file = Path(working_dir, 'server.stderr')

        with open(stdout_file, 'w') as stdout_f, open(stderr_file, 'w') as stderr_f:
            process = Popen(cmd, stdout=stdout_f, stderr=stderr_f, start_new_session=True)

        await asyncio.sleep(0.01)
        if process.poll() is not None:
            extra = ""
            if stdout_file.exists():
                with open(stdout_file, 'r') as f:
                    stdout_content = f.read()
                extra += f"\n--- stdout ---\n{stdout_content}"
            if stderr_file.exists():
                with open(stderr_file, 'r') as f:
                    stderr_content = f.read()
                extra += f"\n--- stderr ---\n{stderr_content}"
            raise Exception(f"process for uri {uri} failed to start {extra}")
        result = dict(uri=new_uri, working_dir=str(working_dir))
        return self.response_or_json(result, return_json)
        
    async def server_exit_cluster(self, index:str, return_json=False):
        cluster, server, status = await self.require_server_at_index(index)
        if not status:
            raise Exception(f"server {server.uri} cannot be told to exit, it is not running")
        leader_uri = status['leader_uri']
        res = await server_exit_cluster(server.uri)
            
        if res.startswith("exited"):
            await stop_server(server.uri)
            server_stopped = True
            
        if leader_uri:
            await send_heartbeats(leader_uri)
            heartbeats_sent = True
            
        # Get final cluster status
        final_status_result = await self.cluster_status(return_json=False)
            
        result = {
                "server_index": str(index),
                "server_uri": server.uri,
                "leader_uri": leader_uri,
                "exit_result": res,
                "final_cluster_status": final_status_result,
            }
        return self.response_or_json(result, return_json)

    
            
        
