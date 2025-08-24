#!/usr/bin/env python
import sys
import asyncio
import json
import argparse
import shutil
import time
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
        # this is a good time to look for servers that have been removed
        # from the cluster
        if cluster_name is None:
            if self.selected is None:
                raise Exception('no cluster name provided and no cluster selected')
            cluster_name = self.selected
        for cname, s_dict in self.clusters.items():
            config_check = None
            if cluster_name is None or cname == cluster_name:
                self.status_records[cname] = stat_dict = {}
                for index, s_config in s_dict.items():
                    try:
                        status = await get_server_status(s_config.uri)
                    except:
                        status = None
                    stat_dict[index] = status
                    if status is not None and config_check is None:
                        try:
                            config_check = await get_cluster_config(s_config.uri)
                        except:
                            pass
                if config_check:
                    exited = []
                    for index, s_config in s_dict.items():
                        #print(f"checking for {s_config.uri} in {config_check.nodes.keys()}")
                        if s_config.uri not in config_check.nodes:
                            #print(f"discovery showed {s_config.uri} in cluster {cname} but no longer configured")
                            exited.append(index)
                    if len(exited) > 0:
                        del s_dict[index] 
                        del stat_dict[index]
                return stat_dict
        return None

    async def query_discover(self, port, host='127.0.0.1', select=True):
        target_uri = f"full://{host}:{port}"
        q_finder = ClusterFinder(uri=target_uri)
        clusters = await q_finder.discover()
        
        if len(clusters) == 0:
            raise Exception(f"Not able to discover cluster at {target_uri}, is it running?")
        cluster_name = next(iter(clusters))
        cluster_data = clusters[cluster_name]
        # Add to internal clusters list
        self.clusters[cluster_name] = cluster_data
        self.selected = cluster_name
        return cluster_name

    async def discover_cluster_files(self, search_dir="/tmp"):
        f_finder = ClusterFinder(root_dir="/tmp")
        clusters = await f_finder.discover()
        if len(clusters) > 0:
            self.clusters.update(clusters)
        if len(clusters) == 1:
            target = next(iter(clusters))
            self.selected = target
            
    def response_or_json(self, data, return_json=False):
        """Utility method to format response data as JSON string if requested"""
        if return_json:
            return json.dumps(data, indent=self.json_indent, default=lambda o:o.__dict__)
        return data
    
    def require_selection(self):
        """Enhanced helper to validate cluster selection, returns structured data"""
        if len(self.clusters) == 0:
            raise Exception("No clusters found, try find_clusters or add_cluster")
        if not self.selected:
            raise Exception("Must select a cluster first")
        return self.clusters[self.selected]
    
    def require_server_at_index(self, index):
        """Enhanced helper to validate server index, returns structured data"""
        cluster = self.require_selection()
        
        if index not in cluster:
            raise Exception(f"Requested server number {index} not found, valid values are {list(cluster.keys())}")
        
        server = cluster[index]
        status = self.status_records.get(self.selected, {}).get(index)
        return cluster, server, status

    async def select_cluster(self, cluster_name):
        if cluster_name not in self.clusters:
            raise Exception(f"cannot select non-existent cluster {cluster_name}")
        self.selected = cluster_name
        await self.get_status()
        
    async def find_clusters(self, search_dir="/tmp", return_json=False):
        await self.discover_cluster_files(search_dir)
        
        # Get current cluster list
        clusters_dict = await self.list_clusters(return_json=False)
        
        # Check if we auto-selected a single cluster
        selected_cluster = None
        if len(self.clusters) == 1:
            cluster_name = next(iter(self.clusters))
            self.selected = cluster_name
            selected_cluster = cluster_name
            
        result = {
            "search_directory": search_dir,
            "query_uri": None,
            "clusters": clusters_dict,
            "selected_cluster": selected_cluster,
        }
        return self.response_or_json(result, return_json)
        
    async def add_cluster(self, port, host='127.0.0.1', return_json=False):
        cluster_name = await self.query_discover(port, host, True)
        clusters_dict = await self.list_clusters(return_json=False)
        target_uri = f"full://{host}:{port}"
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

    
    async def server_status(self, index, return_json=False):
        cluster, server, status = self.require_server_at_index(index)
        # get an up to date status
        status_dict = await self.get_status(self.selected)
        if status_dict[index] is None:
            return None
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

    async def stop_server(self, index, return_json=False):
        """Logic for stopping indexed server"""
        cluster, server, status = self.require_server_at_index(index)
        was_running = status is not None
        if was_running:
            await stop_server(server.uri)
        result = dict(config=server, was_running=was_running)
        return self.response_or_json(result, return_json)

    async def log_stats(self, index, return_json=False):
        cluster, server, status = self.require_server_at_index(index)
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
            result = {
                "local_hostnames": hostnames,
                "local_servers_found": {},
                "initial_cluster_status": initial_status,
                "final_cluster_status": None,
            }
            return self.response_or_json(result, return_json)
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
                stdout = spec['stdout_file']
                if stdout.exists():
                    with open(stdout_file, 'r') as f:
                        stdout_content = f.read()
                    extra += f"\n--- stdout ---\n{stdout_content}"
                stderr = spec['stderr_file']
                if stderr.exists():
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

    async def create_local_cluster(self, cluster_name, directory="/tmp", force=False, return_json=False):
        """Logic for creating a local cluster"""
        # Check if cluster already exists
        f_finder = ClusterFinder(root_dir="/tmp")
        clusters = await f_finder.discover()
        removed = False
        if cluster_name in clusters:
            if force:
                removed = True
                cluster = clusters[cluster_name]
                for index, server in cluster.items():
                    status = await get_server_status(server.uri)
                    if status:
                        await stop_server(server.uri)
                    wd = Path(server.working_dir)
                    shutil.rmtree(wd)
            else:
                result = {
                    "cluster_name": cluster_name,
                    "directory": directory,
                    "force": force,
                    "success": False,
                    "base_port": None,
                    "servers_created": {},
                    "selected": False,
                    "error": f"Already have a cluster with name '{cluster_name}', not creating"
                }
                return self.response_or_json(result, return_json)
            
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
        local_servers = cb.build_local(name=cluster_name, base_port=avail_port)
        cb.setup_local_files(local_servers, directory, overwrite=force)

        # Convert to server dictionary
        server_dict = {}
        servers_created = {}
        for index, server in enumerate(local_servers):
            idx_str = str(index)
            server_dict[idx_str] = server
            servers_created[idx_str] = {
                "uri": server.uri,
                "working_dir": getattr(server, 'working_dir', f"{directory}/full_raft_server.{server.uri.split('/')[-1]}")
            }

        # Add to clusters and select
        self.clusters[cluster_name] = server_dict
        self.selected = cluster_name

        # Update status
        for name in self.clusters:
            await self.get_status(cluster_name=cluster_name)

        result = {
            "cluster_name": cluster_name,
            "directory": directory,
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
            raise Exception(f"Cannot send heartbeat in cluster {self.selected}, no servers are runnig")
        leader = status['leader_uri']
        if leader is None:
            raise Exception(f"Cannot send heartbeat in cluster {self.selected}, no leader has been elected")
        await send_heartbeats(leader)
        result = {
            "cluster_name": self.selected,
            "leader_uri": leader,
        }
        return self.response_or_json(result, return_json)
    
    # NOT CONVERTED
    async def take_snapshot(self, index, return_json=False):
        """Logic for taking snapshot on indexed server"""
        cluster, server, status, error = self.require_server_at_index(index)
        if cluster is None:
            result = {
                "server_index": str(index),
                "server_uri": None,
                "pre_snapshot_status": None,
                "snapshot_result": None,
                "post_snapshot_status": None,
                "error": error
            }
            return self.response_or_json(result, return_json)
        
        try:
            pre_status = await get_server_status(server.uri)
            snap = await take_snapshot(server.uri)
            post_status = await get_server_status(server.uri)
            
            result = {
                "server_index": str(index),
                "server_uri": server.uri,
                "pre_snapshot_status": pre_status,
                "snapshot_result": snap.__dict__ if snap else None,
                "post_snapshot_status": post_status,
                "error": None
            }
        except Exception as e:
            result = {
                "server_index": str(index),
                "server_uri": server.uri,
                "pre_snapshot_status": None,
                "snapshot_result": None,
                "post_snapshot_status": None,
                "error": f"Failed to take snapshot: {str(e)}"
            }
        
        return self.response_or_json(result, return_json)

    async def server_exit_cluster(self, index, return_json=False):
        """Logic for server exiting cluster"""
        cluster, server, status, error = self.require_server_at_index(index)
        if cluster is None:
            result = {
                "server_index": str(index),
                "server_uri": None,
                "leader_uri": None,
                "exit_result": None,
                "server_stopped": False,
                "heartbeats_sent": False,
                "final_cluster_status": {},
                "error": error
            }
            return self.response_or_json(result, return_json)
        
        if not status:
            result = {
                "server_index": str(index),
                "server_uri": server.uri,
                "leader_uri": None,
                "exit_result": None,
                "server_stopped": False,
                "heartbeats_sent": False,
                "final_cluster_status": {},
                "error": f"server {server.uri} is not running, cannot trigger it to exit"
            }
            return self.response_or_json(result, return_json)
        
        try:
            leader_uri = status['leader_uri']
            res = await server_exit_cluster(server.uri)
            server_stopped = False
            heartbeats_sent = False
            
            if res.startswith("exited"):
                await stop_server(server.uri)
                server_stopped = True
            
            if leader_uri:
                await send_heartbeats(leader_uri)
                heartbeats_sent = True
            
            # Get final cluster status
            final_status_result = await self.op_cluster_status(return_json=False)
            
            result = {
                "server_index": str(index),
                "server_uri": server.uri,
                "leader_uri": leader_uri,
                "exit_result": res,
                "server_stopped": server_stopped,
                "heartbeats_sent": heartbeats_sent,
                "final_cluster_status": final_status_result,
                "error": None
            }
        except Exception as e:
            result = {
                "server_index": str(index),
                "server_uri": server.uri,
                "leader_uri": status.get('leader_uri') if status else None,
                "exit_result": None,
                "server_stopped": False,
                "heartbeats_sent": False,
                "final_cluster_status": {},
                "error": str(e)
            }
        
        return self.response_or_json(result, return_json)

    
            
        
