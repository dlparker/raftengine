#!/usr/bin/env python
import sys
import asyncio
import json
from pathlib import Path
from aiocmd import aiocmd
from subprocess import Popen
from pprint import pprint
from collections import defaultdict
src_dir = Path(__file__).parent.parent
logs_dir = Path(src_dir, 'logs')
sys.path.insert(0, str(logs_dir))
src_dir = Path(__file__).parent.parent
sys.path.insert(0, str(src_dir))

from admin_common import (find_local_clusters, get_server_status, get_log_stats, send_heartbeats,
                          get_cluster_config, stop_server, take_snapshot, server_exit_cluster)

class MyCLI(aiocmd.PromptToolkitCmd):


    def __init__(self, my_name="Cluster Commander"):
        super().__init__()
        self.selected = None
        self.prompt = "no selection $ "
        self.clusters = {}
    
    async def do_find_clusters(self, search_dir="/tmp"):
        """Discover clusters by searching directory for counter raft server working directories"""
        res = await find_local_clusters(search_dir)
        for index,key in enumerate(res.keys()):
            config = None
            cdict = res[key]
            rec = dict(discovered=cdict, config=config, discovered_dir=search_dir, cluster_key=key)
            self.clusters[str(index)] = rec
            rec['servers'] = servers = dict()
            for uri,server in cdict.items():
                servers[uri] = dict()
                status = await get_server_status(uri)
                servers[uri]['status'] = status
                host, port = uri.split('/')[-1].split(':')
                servers[uri]['working_dir'] = str(Path(search_dir, f"counter_raft_server.{host}.{port}"))
                if status is not None:
                    servers[uri]['running'] = True
                    if config is None:
                        rec['config']  = await get_cluster_config(uri)
                else:
                    servers[uri]['running'] = False
        await self.do_list_clusters()
        if len(self.clusters) == 1:
            await self.do_select(str(0))

    async def do_add_cluster(self, port, host='127.0.0.1'):
        uri = f"as_raft://{host}:{port}"
        config  = await get_cluster_config(uri)
        if not config:
            print(f"cannot collect cluster config from uri {uri}, got None response")
            return
        c_dict = dict(discovered=None, config=config, discovered_dir=None)
        servers = {}
        uris = list(config.nodes.keys())
        uris.sort()
        cluster_key = ",".join(uris)
        c_dict['cluster_key'] = cluster_key
        for uri in uris:
            status = await get_server_status(uri)
            servers[uri] = dict()
            servers[uri]['status'] = status
            if status is not None:
                servers[uri]['running'] = True
            else:
                servers[uri]['running'] = False
        c_dict['servers'] = servers
        done = False
        for index, ocluster in self.clusters.items():
            if ocluster['cluster_key'] == cluster_key:
                # just update it
                self.clusters[index] = c_dict
                done = True
                break
        if not done:
            index = str(len(self.clusters))
            self.clusters[index] = c_dict
        await self.do_select(index)
        await self.do_show_cluster(index)
        
    async def do_show_cluster(self, index=None):
        if len(self.clusters) == 0:
            print('No clusters found, try find_clusters or add_cluster')
            return
        if not self.selected and index is None:
            print('No cluster selected')
            return
        if index is None:
            index = self.selected
        if index not in self.clusters:
            print(f'No cluster with index {index} found')
            return
            
        cluster = self.clusters[index]
        uris = list(cluster['servers'].keys())
        uris.sort()
        for index,uri in enumerate(uris):
            server = cluster['servers'][uri]
            status = await get_server_status(uri)
            if status:
                print(f" {index} {uri}: running")
            else:
                print(f" {index} {uri}: NOT running")
                
    async def do_list_clusters(self):
        if len(self.clusters) == 0:
            print('No clusters found, try find_clusters or add_cluster')
        for index,cluster in self.clusters.items():
            if cluster['config'] is None:
                print(f"{index}: non-running cluster of servers {','.join(cluster['servers'].keys())}")
            else:
                print(f"{index}: cluster server status list --")
                uris = list(cluster['servers'].keys())
                uris.sort()
                for index,uri in enumerate(uris):
                    server = cluster['servers'][uri]
                    status = await get_server_status(uri)
                    if status:
                        print(f" {index} {uri}: running")
                    else:
                        print(f" {index} {uri}: NOT running")

    async def do_server_status(self, index):
        if not self.selected:
            if len(self.clusters) == 0:
                print('No clusters found, try find_clusters or add_cluster')
                return
            print('No cluster selected')
            return
        cluster = self.clusters[self.selected]
        uris = list(cluster['servers'].keys())
        uris.sort()
        index = int(index)
        if index >= len(uris):
            print(f"Requested server number {index} not found, max is {len(uris)-1}")
            return
        uri = uris[index]
        status = await get_server_status(uri)
        print(json.dumps(status, indent=4))

    async def do_log_stats(self, index):
        if not self.selected:
            if len(self.clusters) == 0:
                print('No clusters found, try find_clusters or add_cluster')
                return
            print('No cluster selected')
            return
        cluster = self.clusters[self.selected]
        uris = list(cluster['servers'].keys())
        uris.sort()
        index = int(index)
        if index >= len(uris):
            print(f"Requested server number {index} not found, max is {len(uris)-1}")
            return
        uri = uris[index]
        log_stats = await get_log_stats(uri)
        print(json.dumps(log_stats.__dict__, indent=4))

    async def do_take_snapshot(self, index):
        if not self.selected:
            if len(self.clusters) == 0:
                print('No clusters found, try find_clusters or add_cluster')
                return
            print('No cluster selected')
            return
        cluster = self.clusters[self.selected]
        uris = list(cluster['servers'].keys())
        uris.sort()
        index = int(index)
        if index >= len(uris):
            print(f"Requested server number {index} not found, max is {len(uris)-1}")
            return
        uri = uris[index]
        pre_status = await get_server_status(uri)
        print("---------- before snapshot -----------")
        print(json.dumps(pre_status, indent=4))
        snap = await take_snapshot(uri)
        print("---------- snapshot -----------")
        print(json.dumps(snap.__dict__, indent=4))
        print("---------- after snapshot -----------")
        post_status = await get_server_status(uri)
        print(json.dumps(post_status, indent=4))
        
    async def do_select(self, index):
        if index not in self.clusters:
            print(f"Supplied index {index} not in clusters array {list(self.clusters.keys())}")
            return 
        self.selected = index
        self.prompt = f"cluster->{index} $ "
        
    async def do_update_status(self):
        if not self.selected:
            if len(self.clusters) == 0:
                print('No clusters found, try find_clusters or add_cluster')
                return
            print('No cluster selected')
            return
        cluster = self.clusters[self.selected]
        new_config = None
        for uri,server in cluster['servers'].items():
            server['status'] = await get_server_status(uri)
            if server['status'] != None and new_config == None:
                cluster['config'] = await get_cluster_config(uri)
        await self.do_list_clusters()
        return
        
    async def do_send_heartbeats(self):
        if not self.selected:
            if len(self.clusters) == 0:
                print('No clusters found, try find_clusters or add_cluster')
                return
            print('No cluster selected')
            return
        cluster = self.clusters[self.selected]
        new_config = None
        for uri,server in cluster['servers'].items():
            status = await get_server_status(uri)
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
        await self.do_list_clusters()
        return
        
    async def do_start_servers(self, hostname='127.0.0.1'):
        if not self.selected:
            if len(self.clusters) == 0:
                print('No clusters found, try find_clusters or add_cluster')
                return
            print('No cluster selected')
            return
        cluster = self.clusters[self.selected]
        local_servers = {}
        for uri,server in cluster['servers'].items():
            host = uri.split('/')[-1].split(':')[0]
            if host == hostname:
                local_servers[uri] = server

        if len(local_servers) == 0:
            print("no local servers to start (did you forget to supply a hostname?)")
            return
        for uri,server in local_servers.items():
            status = await get_server_status(uri)
            if status is None:
                this_dir = Path(__file__).parent
                working_dir = server['working_dir']
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
                    print(f"Server {uri} failed to start")
                    # Read the error logs
                    if stderr_file.exists():
                        with open(stderr_file, 'r') as f:
                            stderr_content = f.read()
                            if stderr_content:
                                print(f"stderr: {stderr_content}")
                    raise Exception(f"Server {uri} failed to start")
        await self.do_update_status()
                
    async def do_stop_cluster(self):
        if not self.selected:
            if len(self.clusters) == 0:
                print('No clusters found, try find_clusters or add_cluster')
                return
            print('No cluster selected')
            return
        cluster = self.clusters[self.selected]
        for uri,server in cluster['servers'].items():
            status = await get_server_status(uri)
            if status != None:
                await stop_server(uri)
        await self.do_update_status()
            
    async def do_server_exit_cluster(self, index):
        if not self.selected:
            if len(self.clusters) == 0:
                print('No clusters found, try find_clusters or add_cluster')
                return
            print('No cluster selected')
            return
        cluster = self.clusters[self.selected]
        uris = list(cluster['servers'].keys())
        uris.sort()
        index = int(index)
        if index >= len(uris):
            print(f"Requested server number {index} not found, max is {len(uris)-1}")
            return
        uri = uris[index]
        res = await server_exit_cluster(uri)
        if res.startswith("exited"):
            await stop_server(uri)
        print(res)
        await send_heartbeats(uri)
        await self.do_update_status()
            
    async def do_stop_server(self, index):
        if not self.selected:
            if len(self.clusters) == 0:
                print('No clusters found, try find_clusters or add_cluster')
                return
            print('No cluster selected')
            return
        cluster = self.clusters[self.selected]
        uris = list(cluster['servers'].keys())
        uris.sort()
        index = int(index)
        if index >= len(uris):
            print(f"Requested server number {index} not found, max is {len(uris)-1}")
            return
        uri = uris[index]
        status = await get_server_status(uri)
        if not status:
            print(f"Server {index} {uri} was already stopped")
        else:
            await stop_server(uri)
        await self.do_update_status()
        
        
if __name__ == "__main__":
    asyncio.run(MyCLI().run())
