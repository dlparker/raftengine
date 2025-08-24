#!/usr/bin/env python
import sys
import asyncio
import json
import argparse
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



base_command_codes = ['list_clusters',]
selected_command_codes = ['cluster_status', 'start_servers', 'stop_cluster', 'send_heartbeats']
indexed_command_codes = ['stop_server', 'server_status', 'log_stats', 'take_snapshot','server_exit_cluster']
command_codes = base_command_codes + selected_command_codes + indexed_command_codes

def run_ops_error(msg):
    print(msg)
    raise SystemExit(1)

async def main(parser, args):

    clusters = None
    if args.files_directory:
        root_dir = args.files_directory
    else:
        root_dir = "/tmp"
    if args.select:
        target = args.select
    else:
        target = None
    if args.query_connect:
        uri = f"full://{args.query_connect}"
        q_finder = ClusterFinder(uri=uri)
        clusters = await q_finder.discover()
    elif args.local_cluster:
        f_finder = ClusterFinder(root_dir=root_dir)
        clusters = await f_finder.discover()
        local_name = None
        if target is not None:
            if target not in clusters:
                run_ops_error(f"requested target cluster '{target}' is not found in {list(clusters.keys())}")
            ctmp = clusters[target]
            if not ctmp['0'].all_local:
                run_ops_error(f"inconsistent request, cluster '{target}' is not a local only cluster")
            else:
                local_name = target
        else:
            for name,servers in clusters.items():
                if servers['0'].all_local:
                    local_name = name
                    break
        if local_name is None:
            run_ops_error("could not find a local cluster")
        else:
            target = local_name
    elif args.create_local_cluster:
        # need to make sure we don't overwrite existing
        f_finder = ClusterFinder(root_dir=root_dir)
        clusters = await f_finder.discover()
        if target is not None:
            if target in clusters:
                run_ops_error(f"Cannot create local cluster with name '{target}', already exists")
            local_name = target
        else:
            candi = "local"
            index = 1
            while candi in clusters:
                candi = f"local_{index}"
                index += 1
            local_name = candi
            
        cluster_cli = ClusterCLI(clusters)
        await cluster_cli.do_create_local_cluster(local_name, root_dir, force=True)
        target = local_name
    if clusters is not None and len(clusters) == 1 and target is None:
        target = next(iter(clusters))
    if args.run_ops != []:
        for cmd in args.run_ops:
            if cmd in selected_command_codes:
                if target is None:
                    run_ops_error(f"the {cmd} command requires a selected cluster")
            if cmd in indexed_command_codes:
                if target is None:
                    run_ops_error(f"the {cmd} command requires a selected cluster")
                if args.index is None:
                    run_ops_error(f"the {cmd} command requires a selected cluster and a server index")
    cluster_cli = ClusterCLI(clusters, target=target)
    if args.run_ops == []:
        await cluster_cli.run()
    if target is not None:
        await cluster_cli.get_status()
    for op in args.run_ops:
        if op == "list_clusters":
            if args.json:
                print(await cluster_cli._logic_list_clusters(return_json=True))
            else:
                await cluster_cli.do_list_clusters()
        elif op == "cluster_status":
            if args.json:
                print(await cluster_cli._logic_cluster_status(return_json=True))
            else:
                await cluster_cli.do_cluster_status()
        elif op == "start_servers":
            if args.json:
                print(await cluster_cli._logic_start_servers(return_json=True))
            else:
                await cluster_cli.do_start_servers()
        elif op == "stop_cluster":
            if args.json:
                print(await cluster_cli._logic_stop_cluster(return_json=True))
            else:
                await cluster_cli.do_stop_cluster()
        elif op == "send_heartbeats":
            if args.json:
                print(await cluster_cli._logic_send_heartbeats(return_json=True))
            else:
                await cluster_cli.do_send_heartbeats()
        elif op == "stop_server":
            if args.json:
                print(await cluster_cli._logic_stop_server(args.index, return_json=True))
            else:
                await cluster_cli.do_stop_server(args.index)
        elif op == "server_status":
            if args.json:
                print(await cluster_cli._logic_server_status(args.index, return_json=True))
            else:
                stats = await cluster_cli.do_server_status(args.index)
        elif op == "log_stats":
            if args.json:
                print(await cluster_cli._logic_log_stats(args.index, return_json=True))
            else:
                stats = await cluster_cli.do_log_stats(args.index)
        elif op == "take_snapshot":
            if args.json:
                print(await cluster_cli._logic_take_snapshot(args.index, return_json=True))
            else:
                stats = await cluster_cli.do_take_snapshot(args.index)
        elif op == "server_exit_cluster":
            if args.json:
                print(await cluster_cli._logic_server_exit_cluster(args.index, return_json=True))
            else:
                stats = await cluster_cli.do_server_exit_cluster(args.index)


class MyCommander(aiocmd.PromptToolkitCmd):


    def do_help(self):
        print()
        print(self.doc_header)
        print("=" * len(self.doc_header))
        print()

        get_usage = lambda command: self._get_command_usage(command, *self._get_command_args(command))
        max_usage_len = max([len(get_usage(command)) for command in self.command_list])
        ordered_list = []
        for item in self.method_order:
            ordered_list.append(item)
        for item in self.command_list:
            if item not in ordered_list:
                ordered_list.append(item)

        for command in ordered_list:
            command_doc = self._get_command(command).__doc__
            print(("%-" + str(max_usage_len + 2) + "s%s") % (get_usage(command), command_doc or ""))

    
class ClusterCLI(MyCommander):

    method_order = []  

    def __init__(self, clusters=None, target=None):
        super().__init__()
        if clusters is None:
            clusters = {}
        self.clusters = clusters
        self.status_records = {}
        self.selected = target
        if target is not None:
            self.prompt = f"{target} $ "
        else:
            self.prompt = "no selection $ "

    async def get_status(self, cluster_name=None):
        # this is a good time to look for servers that have been removed
        # from the cluster
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
        uri = f"full://{host}:{port}"
        q_finder = ClusterFinder(uri=uri)
        clusters = await q_finder.discover()
        if len(clusters) > 0:
            target = next(iter(clusters))
        self.clusters[target] = clusters[target]
        if select:
            await self.set_selected(target)
            await self.get_status()

    async def set_selected(self, target):
        if target not in self.clusters:
            print(f"{target} not in {list(self.clusters.keys())}")
            return
        self.selected = target
        self.prompt = f"{target} $ "
        await self.get_status(cluster_name=target)

    async def discover_cluster_files(self, search_dir="/tmp"):
        f_finder = ClusterFinder(root_dir="/tmp")
        clusters = await f_finder.discover()
        if len(clusters) > 0:
            self.clusters.update(clusters)
        if len(clusters) == 1:
            target = next(iter(clusters))
            await self.set_selected(target)
            
    async def do_find_clusters(self, search_dir="/tmp"):
        """
        Search for existing clusters by examining directories and files in the "search_dir"
        using the convention that a server's working directory is named "full_raft_server.host.port".
        Any directory matching that pattern will be examined to see if there is a server_config.json
        file that describes the server and the cluster it belongs to. Any clusters found this way
        will be added to the internal list of clusters.
        This will work for any server defined in any cluster, but if the cluster is not running,
        then the information is likely
        to be out of date."""
        await self.discover_cluster_files(search_dir)
        await self.do_list_clusters()
        if len(self.clusters) == 1:
            await self.do_select(str(0))
            await self.do_cluster_status(index)

    async def do_add_cluster(self, port, host='127.0.0.1'):
        """
        Add an existing cluster to the internal list by querying the server at the provided host and port.
        If the server is running the details of the cluster will be collected and recorded. If the server
        is not running try using the find_clusters command to find at least the local saved information
        about the cluster."""
        index = await self.query_discover(port, host)
        if index:
            await self.do_select(index)
            await self.do_cluster_status(index)

    async def do_list_clusters(self):
        """
        Show the internal list of clusters.  """
        result = await self._logic_list_clusters(return_json=False)
        
        if result["total_clusters"] == 0:
            print('No clusters found, try find_clusters or add_cluster')
            return
            
        for name, cluster_data in result["clusters"].items():
            uris = [server_data["uri"] for server_data in cluster_data["servers"].values()]
            print(f"{name}: {cluster_data['status']} cluster of servers {','.join(uris)}")

    async def do_select(self, name):
        """
        Select the named cluster as the active cluster for future commands"""
        result = await self._logic_select(name, return_json=False)
        
        if not result["success"]:
            print(result["error"])
        # Note: _logic_select already calls set_selected internally

    async def do_cluster_status(self, name=None):
        """
        Overview of the status of named or currently selected cluster, including basic server status."""
        result = await self._logic_cluster_status(name, return_json=False)
        
        if "error" in result and result["error"]:
            print(result["error"])
            return
        
        for index, server_data in result["servers"].items():
            status_text = "running" if server_data["running"] else "NOT running"
            print(f" {index} {server_data['uri']}: {status_text}")
                
    async def do_update_cluster(self, name=None):
        """
        Refresh the configuration and status data for the named or currently selected cluster and its servers"""
        if name is None:
            cluster = self.c_preamble()
            if not cluster:
                return
            name = self.selected
        else:
            if len(self.clusters) == 0:
                print('No clusters found, try find_clusters or add_cluster')
                return
            if name not in self.clusters:
                print(f"No cluster named {name} found, valid are {','.join(list(self.clusters.keys()))}")
                return
            cluster = self.clusters[name]
        for index,server in cluster.items():
            config = await get_cluster_config(server.uri)
            if config is not None:
                host,port = server.uri.split("/")[-1].split(':')
                await self.query_discover(port, host)
                await self.get_status(cluster_name=name)
                break
        await self.do_cluster_status(name)
        
    async def do_start_servers(self, hostname='127.0.0.1'):
        """
        Start any servers in the currently selected cluster that match the provided hostname. This
        only works for servers configured to run on the local host. You have to provide the hostname
        because the stored cluster config does not provide a way to identify which machine matches which
        hostname"""
        cluster = self.c_preamble()
        if not cluster:
            return
        local_servers = {}
        for index,server in cluster.items():
            host = server.uri.split('/')[-1].split(':')[0]
            if host == hostname:
                local_servers[server.uri] = server

        if len(local_servers) == 0:
            print("no local servers to start (did you forget to supply a hostname?)")
            return
        for uri,server in local_servers.items():
            status = await get_server_status(uri)
            if status is None:
                this_dir = Path(__file__).parent
                working_dir = server.working_dir
                sfile = Path(this_dir, 'run_server.py')
                cmd = [str(sfile), "-w", working_dir, ]
                stdout_file = Path(working_dir,'server.stdout')
                stderr_file = Path(working_dir,'server.stderr')
                with open(stdout_file, 'w') as stdout_f, open(stderr_file, 'w') as stderr_f:
                    process = Popen(cmd, stdout=stdout_f,stderr=stderr_f, start_new_session=True)
                # Wait a moment to see if process starts successfully
                await asyncio.sleep(0.1)
                if process.poll() is None:  # Process is still running
                    if False:
                        print(f"Server {uri} started successfully")
                        print(f"  stdout: {stdout_file}")
                        print(f"  stderr: {stderr_file}")
                else:
                    print(f"Server {server.uri} failed to start")
                    # Read the error logs
                    if stderr_file.exists():
                        with open(stderr_file, 'r') as f:
                            stderr_content = f.read()
                            if stderr_content:
                                print(f"stderr: {stderr_content}")
                    raise Exception(f"Server {server.uri} failed to start")
        await self.do_cluster_status()
                
    async def do_stop_cluster(self):
        """
        Stop all the servers in the currently selected cluster. This works for servers on any machine
        because it uses an RPC to tell the server to stop."""
        
        cluster = self.c_preamble()
        if not cluster:
            return
        for index,server in cluster.items():
            status = await get_server_status(server.uri)
            if status != None:
                await stop_server(server.uri)
        await self.do_cluster_status()
    
    async def do_server_status(self, index):
        """
        Get the status dictionary for the the indexed server in the currently selected cluster"""
        result = await self._logic_server_status(index, return_json=False)
        
        if "error" in result and result["error"]:
            print(result["error"])
            return
        
        print(json.dumps(result["status"], indent=4))

    async def do_log_stats(self, index):
        """
        Get the LogStats object for the the indexed server in the currently selected cluster"""
        result = await self._logic_log_stats(index, return_json=False)
        
        if "error" in result and result["error"]:
            print(result["error"])
            return
        
        print(json.dumps(result["log_stats"], indent=4))

    async def do_take_snapshot(self, index):
        """
        Run the snapshot creation sequence on the indexed server in the currently selected cluster"""
        cluster,server,status = self.s_preamble(index)
        if not cluster:
            return
        pre_status = await get_server_status(server.uri)
        print("---------- before snapshot -----------")
        print(json.dumps(pre_status, indent=4))
        snap = await take_snapshot(server.uri)
        print("---------- snapshot -----------")
        print(json.dumps(snap.__dict__, indent=4))
        print("---------- after snapshot -----------")
        post_status = await get_server_status(server.uri)
        print(json.dumps(post_status, indent=4))
        
    async def do_stop_server(self, index):
        """
        Tell the indexed server in the currently selected cluster via RPC to stop"""
        cluster,server,status = self.s_preamble(index)
        if not cluster:
            return
        if not status:
            print(f"Server {index} {server.uri} was already stopped")
        else:
            await stop_server(server.uri)
        await self.do_cluster_status()
        
    async def do_server_exit_cluster(self, index):
        """
        Send an RPC to the indexed server in the currently selected cluster to tell it to
        remove itself from the cluster, which requires leader mediated log changes to
        complete"""
        cluster,server,status = self.s_preamble(index)
        if not cluster:
            return
        if not status:
            print(f"server {server.uri} is not running, cannot trigger it to exit")
        leader_uri = status['leader_uri']
        res = await server_exit_cluster(server.uri)
        if res.startswith("exited"):
            await stop_server(server.uri)
        print(res)
        await send_heartbeats(leader_uri)
        await self.do_cluster_status()
        
    async def do_send_heartbeats(self):
        """
        Find the leader of the currently selected cluster and tell it to send heartbeats. This is only
        ever necessary if you have chosen to configure the cluster with slow heartbeats for development
        purposes. Typically this is done when you have a task to do that would be impeeded by the constant
        heartbeat RPCs or that might trigger an election because your action impeed the heartbeat/timeout
        logic. Another potential reason is that you want to run DEBUG level logic and you don't want the
        constant heartbeat message logging to spam the output."""
        cluster = self.c_preamble()
        if not cluster:
            return
        new_config = None
        for index,server in cluster.items():
            status = await get_server_status(server.uri)
            if status:
                break
        if status is None:
            print('no servers running in selected cluster')
            return
        leader = status['leader_uri']
        if leader is None:
            print('selected cluster has not elected a leader')
            return
        await send_heartbeats(leader)
        print(f"leader {leader} told to do heartbeats")
        return

    async def do_create_local_cluster(self, cluster_name, directory="/tmp", force=False):
        """
        Create a new cluster with name, as a local only cluster, for testing, debug, etc.
        The server control files will be placed in the provided directory (/tmp default)
        and the generated uris will use the loopback interface (127.0.0.1). If you want
        the cluster to survive reboots, supply something for directory that is not in /tmp.
        If you want the cluster to be accessible from other machines, use "create_cluster" instead."""
        f_finder = ClusterFinder(root_dir="/tmp")
        clusters = await f_finder.discover()
        if cluster_name in clusters:
            print(f"Already have a cluster with name '{cluster_name}', not creating")
            return
        avail_port = None
        try_port = 50100
        while True:
            bad_pass = False
            for name,servers in clusters.items():
                for index, server in servers.items():
                    host,port = server.uri.split("/")[-1].split(':')
                    if port == try_port:
                        try_port += 100
                        bad_pass = True
                        break
                if bad_pass:
                    break
            if not bad_pass:
                avail_port = try_port
                break
        cb = ClusterBuilder()
        local_servers = cb.build_local(name=cluster_name, base_port=avail_port)
        cb.setup_local_files(local_servers, "/tmp", overwrite=force)
        server_dict = {}
        for index, server in enumerate(local_servers):
            server_dict[str(index)] = server
        self.clusters[cluster_name] = server_dict
        await self.set_selected(cluster_name)
        for name in self.clusters:
            await self.get_status(cluster_name=cluster_name)
        return

    def c_preamble(self):
        if not self.selected:
            if len(self.clusters) == 0:
                print('No clusters found, try find_clusters or add_cluster')
                return None
            print('No cluster selected')
            return None
        cluster = self.clusters[self.selected]
        return cluster
        
    def s_preamble(self, index):
        if not self.selected:
            if len(self.clusters) == 0:
                print('No clusters found, try find_clusters or add_cluster')
                return None,None,None
            print('No cluster selected')
            return None,None,None
        cluster = self.clusters[self.selected]
        if index not in cluster:
            print(f"Requested server number {index} not found, valid values are {list(cluster.keys())}")
            return None,None,None
        return cluster,cluster[index], self.status_records[self.selected][index]
    
    def _format_json_response(self, data, return_json=False):
        """Utility method to format response data as JSON string if requested"""
        if return_json:
            return json.dumps(data, indent=4)
        return data
    
    def _create_error_response(self, error_message, return_json=False):
        """Utility method to create consistent error responses"""
        error_data = {"success": False, "error": error_message}
        return self._format_json_response(error_data, return_json)
    
    def _validate_cluster_selected(self):
        """Enhanced helper to validate cluster selection, returns structured data"""
        if len(self.clusters) == 0:
            return None, "No clusters found, try find_clusters or add_cluster"
        if not self.selected:
            return None, "No cluster selected"
        return self.clusters[self.selected], None
    
    def _validate_server_index(self, index):
        """Enhanced helper to validate server index, returns structured data"""
        cluster, error = self._validate_cluster_selected()
        if cluster is None:
            return None, None, None, error
        
        if index not in cluster:
            return None, None, None, f"Requested server number {index} not found, valid values are {list(cluster.keys())}"
        
        server = cluster[index]
        status = self.status_records.get(self.selected, {}).get(index)
        return cluster, server, status, None

    async def _logic_list_clusters(self, return_json=False):
        """Logic for listing clusters with their running status"""
        if len(self.clusters) == 0:
            result = {
                "clusters": {},
                "total_clusters": 0
            }
            return self._format_json_response(result, return_json)
        
        clusters_data = {}
        for name, cluster in self.clusters.items():
            await self.get_status(name)
            running = False
            servers_data = {}
            
            for index, s_config in cluster.items():
                record = self.status_records[name][index]
                is_running = record is not None
                if is_running:
                    running = True
                
                servers_data[index] = {
                    "uri": s_config.uri,
                    "running": is_running,
                    "working_dir": getattr(s_config, 'working_dir', None)
                }
            
            clusters_data[name] = {
                "status": "running" if running else "non-running",
                "servers": servers_data
            }
        
        result = {
            "clusters": clusters_data,
            "total_clusters": len(clusters_data)
        }
        return self._format_json_response(result, return_json)

    async def _logic_select(self, name, return_json=False):
        """Logic for selecting a cluster as the active cluster"""
        if name not in self.clusters:
            result = {
                "success": False,
                "selected_cluster": None,
                "available_clusters": list(self.clusters.keys()),
                "error": f"Supplied name {name} not in clusters array {list(self.clusters.keys())}"
            }
            return self._format_json_response(result, return_json)
        
        await self.set_selected(name)
        result = {
            "success": True,
            "selected_cluster": name,
            "available_clusters": list(self.clusters.keys()),
            "error": None
        }
        return self._format_json_response(result, return_json)

    async def _logic_server_status(self, index, return_json=False):
        """Logic for getting server status dictionary"""
        cluster, server, status, error = self._validate_server_index(index)
        if cluster is None:
            result = {
                "server_index": str(index),
                "server_uri": None,
                "status": None,
                "error": error
            }
            return self._format_json_response(result, return_json)
        
        result = {
            "server_index": str(index),
            "server_uri": server.uri,
            "status": status,
            "error": None
        }
        return self._format_json_response(result, return_json)

    async def _logic_cluster_status(self, name=None, return_json=False):
        """Logic for getting cluster status overview"""
        if len(self.clusters) == 0:
            result = {
                "cluster_name": None,
                "servers": {},
                "total_servers": 0,
                "running_servers": 0,
                "error": "No clusters found, try find_clusters or add_cluster"
            }
            return self._format_json_response(result, return_json)
        
        if not self.selected and name is None:
            result = {
                "cluster_name": None,
                "servers": {},
                "total_servers": 0,
                "running_servers": 0,
                "error": "No cluster selected"
            }
            return self._format_json_response(result, return_json)
        
        if name is None:
            name = self.selected
            
        if name not in self.clusters:
            result = {
                "cluster_name": name,
                "servers": {},
                "total_servers": 0,
                "running_servers": 0,
                "error": f"No cluster with name {name} found"
            }
            return self._format_json_response(result, return_json)
        
        cluster = self.clusters[name]
        await self.get_status(name)
        
        servers_data = {}
        running_count = 0
        
        for index, s_config in cluster.items():
            record = self.status_records[name][index]
            is_running = record is not None
            if is_running:
                running_count += 1
                
            servers_data[index] = {
                "uri": s_config.uri,
                "running": is_running,
                "status_details": record
            }
        
        result = {
            "cluster_name": name,
            "servers": servers_data,
            "total_servers": len(servers_data),
            "running_servers": running_count,
            "error": None
        }
        return self._format_json_response(result, return_json)

    async def _logic_log_stats(self, index, return_json=False):
        """Logic for getting LogStats object for indexed server"""
        cluster, server, status, error = self._validate_server_index(index)
        if cluster is None:
            result = {
                "server_index": str(index),
                "server_uri": None,
                "log_stats": None,
                "error": error
            }
            return self._format_json_response(result, return_json)
        
        try:
            log_stats = await get_log_stats(server.uri)
            log_stats_dict = log_stats.__dict__ if log_stats else None
        except Exception as e:
            result = {
                "server_index": str(index),
                "server_uri": server.uri,
                "log_stats": None,
                "error": f"Failed to get log stats: {str(e)}"
            }
            return self._format_json_response(result, return_json)
        
        result = {
            "server_index": str(index),
            "server_uri": server.uri,
            "log_stats": log_stats_dict,
            "error": None
        }
        return self._format_json_response(result, return_json)

    async def _logic_take_snapshot(self, index, return_json=False):
        """Logic for taking snapshot on indexed server"""
        cluster, server, status, error = self._validate_server_index(index)
        if cluster is None:
            result = {
                "server_index": str(index),
                "server_uri": None,
                "pre_snapshot_status": None,
                "snapshot_result": None,
                "post_snapshot_status": None,
                "error": error
            }
            return self._format_json_response(result, return_json)
        
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
        
        return self._format_json_response(result, return_json)

    async def _logic_stop_server(self, index, return_json=False):
        """Logic for stopping indexed server"""
        cluster, server, status, error = self._validate_server_index(index)
        if cluster is None:
            result = {
                "server_index": str(index),
                "server_uri": None,
                "was_running": False,
                "stop_success": False,
                "final_cluster_status": {},
                "error": error
            }
            return self._format_json_response(result, return_json)
        
        was_running = status is not None
        stop_success = False
        
        if was_running:
            try:
                await stop_server(server.uri)
                stop_success = True
            except Exception as e:
                result = {
                    "server_index": str(index),
                    "server_uri": server.uri,
                    "was_running": was_running,
                    "stop_success": False,
                    "final_cluster_status": {},
                    "error": f"Failed to stop server: {str(e)}"
                }
                return self._format_json_response(result, return_json)
        
        # Get final cluster status
        final_status_result = await self._logic_cluster_status(return_json=False)
        
        result = {
            "server_index": str(index),
            "server_uri": server.uri,
            "was_running": was_running,
            "stop_success": stop_success,
            "final_cluster_status": final_status_result,
            "error": None
        }
        return self._format_json_response(result, return_json)
    
for name, method in ClusterCLI.__dict__.items():
    if name.startswith("do_"):
        ClusterCLI.method_order.append(name[3:])
        
if __name__ == "__main__":
    
    parser = argparse.ArgumentParser(description='Counters Raft Cluster Admin')

    group = parser.add_mutually_exclusive_group(required=False)
    
    group.add_argument('--local-cluster', '-l', action="store_true",
                        help='Find a test cluster with servers all on this machine in --files-directory directory or /tmp')
    
    group.add_argument('--query-connect', '-q', 
                        help='Find cluster by quering provided address data in form host:port')

    group.add_argument('--create-local-cluster', action="store_true",
                        help='Create a test cluster with servers all on this machine in --files-directory directory or /tmp')
    
    parser.add_argument('--files-directory', '-d', 
                        help='Filesystem location of where server working directories might be found')
    
    parser.add_argument('--select', '-s', 
                        help='Select cluster by name, must be used only with one of the cluster finder options')

    parser.add_argument('--index', '-i', 
                        help='Index of server in select cluster for command (no effect on interactive ops)')

    parser.add_argument('--run-ops', choices=command_codes, action="append", default=[], 
                                help="Run the requested command an exit without starting interactive loop, can be used multiple times")
    parser.add_argument('--json', '-j',  action="store_true",
                        help='Output results in json format, only applies to --run-ops commands')
    # Parse arguments
    args = parser.parse_args()
    
    
    asyncio.run(main(parser, args))
