#!/usr/bin/env python
import sys
import asyncio
import json
import argparse
import shutil
import traceback
from pathlib import Path
from aiocmd import aiocmd
from subprocess import Popen
from pprint import pprint
from collections import defaultdict
from dataclasses import asdict

from ops.cluster_mgr import ClusterMgr
#from ops.admin_common import (get_server_status, get_log_stats, send_heartbeats,
#                              get_cluster_config, stop_server, take_snapshot, server_exit_cluster)

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

    def __init__(self, manager):
        super().__init__()
        self.manager = manager
        if self.manager.selected is not None:
            self.prompt = f"{self.manager.selected} $ "
        else:
            self.prompt = "no selection $ "

    async def do_find_clusters(self, search_dir="/tmp"):
        """
        Search for existing clusters by examining directories and files in the "search_dir"
        using the convention that a server's working directory is named "sum_raft_server.host.port".
        Any directory matching that pattern will be examined to see if there is a server_config.json
        file that describes the server and the cluster it belongs to. Any clusters found this way
        will be added to the internal list of clusters.
        This will work for any server defined in any cluster, but if the cluster is not running,
        then the information is likely
        to be out of date."""
        try:
            result = await self.manager.discover_cluster_files(search_dir)
        except Exception as e: 
            print(f"Error searching directory '{search_dir}': {e}")
            return
        print(f"Searched directory: {search_dir}")
        for name, cluster in self.manager.clusters.items():
            specs = []
            if name == self.manager.selected:
                selected = "Selected"
            else:
                selected = ""
            print(f"{name}: {len(cluster)} servers: {selected}")
            for index,config in cluster.items():
                status = self.manager.status_records.get(index, None)
                if status:
                    pid = status['pid']
                else:
                    pid = None
                print(f"\tindex={index}, uri:{config.uri}, working_dir:{config.working_dir}, pid={pid}")
        if len(self.manager.clusters) == 1:
            self.manager.selected = next(iter(self.manager.clusters))
        elif len(self.manager.clusters) == 0:
            print(f"No clusters found in searched directory {search_dir}")
        elif self.manager.selected is None:
            print(f"Multiple clusters found. Use 'select <index>' to choose one.")
    
    async def do_add_cluster(self, port, host='127.0.0.1'):
        """
        Add an existing cluster to the internal list by querying the server at the provided host and port.
        If the server is running the details of the cluster will be collected and recorded. If the server
        is not running try using the find_clusters command to find at least the local saved information
        about the cluster."""
        try:
            result = await self.manager.add_cluster(port, host, return_json=False)
        except Exception as e:  
            print(f"Error quering '{host}:{port}' for cluster: {e}")
            return
        await self.do_cluster_status()

    async def do_list_clusters(self):
        """
        Show the list of known clusters.  """
        
        if len(self.manager.clusters) == 0:
            print('No clusters found, try find_clusters or add_cluster')
            return
            
        for name, cluster_data in self.manager.clusters.items():
            uris = [config.uri for config in cluster_data.values()]
            print(f"{name}: cluster of servers {','.join(uris)}")

    async def do_select(self, name):
        """
        Select the named cluster as the active cluster for future commands"""
        if name not in self.manager.clusters:
            print(f"No cluster named {name} exists. Try list_clusters")
            return
        self.manager.selected = name
        print(f"Cluster {name} selected")

    async def do_cluster_status(self, name=None):
        """
        Overview of the status of named or currently selected cluster, including basic server status."""
        if not self.manager.selected and name is None:
            print(f"Either supply a cluster name, or select one")
            return
        if name is None:
            name = self.manager.selected
        cluster = self.manager.clusters[name]
        status_dict = await self.manager.get_status(name)
        for index,config in cluster.items():
            status = status_dict[index]
            if status:
                pid_str = f"running as {status['pid']}"
            else:
                pid_str = "not running"
            print(f"\tindex={index}, uri:{config.uri}, working_dir:{config.working_dir}, {pid_str}")
                
    async def do_start_servers(self, hostnames=['127.0.0.1',]):
        """
        Start any servers in the currently selected cluster that match the provided hostname list. This
        only works for servers configured to run on the local host. You have to provide the hostnames
        because the stored cluster config does not provide a way to identify which machine matches which
        hostname"""
        try:
            result = await self.manager.start_servers(hostnames, wait_for_status=True)
        except Exception as e:
            print(f"Error starting servers : {e}")
            return 
        # Show final cluster status
        await self.do_cluster_status()
        
                
    async def do_stop_cluster(self):
        """
        Stop all the servers in the currently selected cluster. This works for servers on any machine
        because it uses an RPC to tell the server to stop."""
        try:
            result = await self.manager.stop_cluster()
        except Exception as e:
            print(f"Error stopping servers : {e}")
            return
        await self.do_cluster_status()
    
    async def do_server_status(self, index):
        """
        Get the status dictionary for the the indexed server in the currently selected cluster"""
        try:
            result = await self.manager.server_status(index)
        except Exception as e:
            print(f"Error getting status of server {index} : {e}")
            return
        print(json.dumps(result, indent=4))

    async def do_log_stats(self, index):
        """
        Get the LogStats object for the the indexed server in the currently selected cluster"""
        try:
            result = await self.manager.log_stats(index)
        except Exception as e:
            print(f"Error getting log stats of server {index} : {e}")
            return
        print(json.dumps(asdict(result), indent=4))

    async def do_stop_server(self, index):
        """
        Tell the indexed server in the currently selected cluster via RPC to stop"""
        try:
            result = await self.manager.stop_server(index)
        except Exception as e:
            print(f"Error stopping server {index} : {e}")
            return
        #print(json.dumps(result, indent=4, default= lambda o:o.__dict__))
        await self.do_cluster_status()
        
    async def do_send_heartbeats(self):
        """
        Find the leader of the currently selected cluster and tell it to send heartbeats. This is only
        ever necessary if you have chosen to configure the cluster with slow heartbeats for development
        purposes. Typically this is done when you have a task to do that would be impeeded by the constant
        heartbeat RPCs or that might trigger an election because your action impeed the heartbeat/timeout
        logic. Another potential reason is that you want to run DEBUG level logic and you don't want the
        constant heartbeat message logging to spam the output."""
        try:
            result = await self.manager.send_heartbeats()
        except Exception as e:
            print(f"Error sending heartbeats : {e}")
            return
        print("Heartbeats Sent")

    async def do_take_snapshot(self, index):
        """
        Run the snapshot creation sequence on the indexed server in the currently selected cluster"""
        try:
            result = await self.manager.take_snapshot(index)
        except Exception as e:
            print(f"Error taking snapshot at server {index} : {e}")
            return
        print(f"Snapshot {result['snapshot']}")
        
    async def do_new_server(self, hostname='127.0.0.1'):
        """
        Configure a new server to run on the local maching using the provided hostname,
        setup the working directory, start the server and tell it to join the cluster
        by contacting the leader and asking to be added. 
        """
        try:
            result = await self.manager.new_server(hostname)
        except Exception as e:
            print(f"Error adding new server : {e}")
            return
        print(f"New server at uri {result['uri']} in working_dir {result['working_dir']}")
        index = list(self.manager.clusters[self.manager.selected].keys())[-1]
        await self.manager.server_status(index)
        
    async def do_server_exit_cluster(self, index):
        """
        Send an RPC to the indexed server in the currently selected cluster to tell it to
        remove itself from the cluster, which requires leader mediated log changes to
        complete"""
        try:
            result = await self.manager.server_exit_cluster(index)
        except Exception as e:
            print(f"Error trying to make server {index} exit cluster: {e}")
            return
        await self.do_cluster_status()
        
    async def do_create_local_cluster(self, cluster_name, directory="/tmp", force=False):
        """
        Create a new cluster with name, as a local only cluster, for testing, debug, etc.
        The server control files will be placed in the provided directory (/tmp default)
        and the generated uris will use the loopback interface (127.0.0.1). If you want
        the cluster to survive reboots, supply something for directory that is not in /tmp.
        If you want the cluster to be accessible from other machines, use "create_cluster" instead."""

        try:
            target_dir = Path(directory, cluster_name)
            result = await self.manager.create_local_cluster(cluster_name, str(target_dir), force=force)
        except Exception as e:
            print(f"Error creating cluster : {e}")
            return
        await self.do_cluster_status(cluster_name)

    
for name, method in ClusterCLI.__dict__.items():
    if name.startswith("do_"):
        ClusterCLI.method_order.append(name[3:])
        
