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

from ops.admin_common import (find_local_clusters, get_server_status, get_log_stats, send_heartbeats,
                          get_cluster_config, stop_server, take_snapshot, server_exit_cluster)
from ops.admin_common import ClusterBuilder, ClusterFinder


async def main(args):

    clusters = None
    target = None
    if args.query_connect:
        uri = f"full://{args.query_connect}"
        q_finder = ClusterFinder(uri=uri)
        clusters = await q_finder.discover()
    elif args.discover:
        f_finder = ClusterFinder(root_dir=args.discover)
        clusters = await f_finder.discover()
    elif args.local_cluster:
        f_finder = ClusterFinder(root_dir="/tmp")
        clusters = await f_finder.discover()
        for name,servers in clusters.items():
            if servers['0'].all_local:
                target = name
                break
        if target is None:
            cb = ClusterBuilder()
            local_servers = cb.build_local(name="auto_local", base_port=50100)
            cb.setup_local_files(local_servers, "/tmp", overwrite=args.force)
            clusters["auto_local"] = local_servers
    if clusters is not None and len(clusters) == 1 and target is None:
        target = next(iter(clusters))
    cluster_cli = ClusterCLI(clusters, target=target)
    await cluster_cli.get_status()
    await cluster_cli.run()
    
class ClusterCLI(aiocmd.PromptToolkitCmd):

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
                    status = await get_server_status(s_config.uri)
                    stat_dict[index] = status
                    if status and config_check is None:
                        config_check = await get_cluster_config(s_config.uri)
                if config_check:
                    exited = []
                    for index, s_config in s_dict.items():
                        #print(f"checking for {s_config.uri} in {config_check.nodes.keys()}")
                        if s_config.uri not in config_check.nodes:
                            print(f"discovery showed {s_config.uri} in cluster {cname} but no longer configured")
                            exited.append(index)
                    if len(exited) > 0:
                        del s_dict[index] 
                        del stat_dict[index] 
        
    async def find_or_create_local(self):
        f_finder = ClusterFinder(root_dir="/tmp")
        clusters = f_finder.discover()
        if len(clusters) > 0:
            self.clusters.update(clusters)
        for name,servers in clusters:
            if servers[0].all_local:
                target = name
                break
        if target is not None:
            await self.set_selected(target)
            return
        target = "local"
        local_servers = cb.build_local(name=target, base_port=50100)
        cb.setup_local_files(local_servers, "/tmp", overwrite=args.force)
        self.clusters[target] = local_servers
        await self.set_selected(target)
        for target in self.clusters:
            await self.get_status(cluster_name=target)
        return

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
        clusters = f_finder.discover()
        if len(clusters) > 0:
            self.clusters.update(clusters)
        if len(clusters) == 1:
            target = next(iter(clusters))
            await self.set_selected(target)
            
    async def do_find_clusters(self, search_dir="/tmp"):
        await self.discover_cluster_files(search_dir)
        await self.do_list_clusters()
        if len(self.clusters) == 1:
            await self.do_select(str(0))
            await self.do_show_cluster(index)

    async def do_show_cluster(self, name=None):
        if len(self.clusters) == 0:
            print('No clusters found, try find_clusters or add_cluster')
            return
        if not self.selected and name is None:
            print('No cluster selected')
            return
        if name is None:
            name = self.selected
        if name not in self.clusters:
            print(f'No cluster with name {name} found')
            return
        cluster = self.clusters[name]
        await self.get_status(name)
        for index, s_config in cluster.items():
            record = self.status_records[name][index]
            if record:
                print(f" {index} {s_config.uri}: running")
            else:
                print(f" {index} {s_config.uri}: NOT running")
                
    async def do_add_cluster(self, port, host='127.0.0.1'):
        index = await self.query_discover(port, host)
        if index:
            await self.do_select(index)
            await self.do_show_cluster(index)

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
        
    async def do_list_clusters(self):
        if len(self.clusters) == 0:
            print('No clusters found, try find_clusters or add_cluster')
        for name,cluster in self.clusters.items():
            await self.get_status(name)
            running = False
            for index, s_config in cluster.items():
                record = self.status_records[name][index]
                if record:
                    running = True
                    break
            if running:
                flag = "running"
            else:
                flag = "non-running"
            uris = [config.uri for config in cluster.values()]
            print(f"{name}: {flag} cluster of servers {','.join(uris)}")

    async def do_server_status(self, index):
        cluster,server,status = self.s_preamble(index)
        if not cluster:
            return
        print(json.dumps(status, indent=4))

    async def do_log_stats(self, index):
        cluster,server,status = self.s_preamble(index)
        if not cluster:
            return
        log_stats = await get_log_stats(server.uri)
        print(json.dumps(log_stats.__dict__, indent=4))

    async def do_take_snapshot(self, index):
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
        
    async def do_select(self, name):
        if name not in self.clusters:
            print(f"Supplied name {name} not in clusters array {list(self.clusters.keys())}")
            return 
        await self.set_selected(name)

    async def do_update_cluster(self, name=None):
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
        await self.do_show_cluster(name)
    
    async def do_send_heartbeats(self):
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

    async def do_stop_cluster(self):
        cluster = self.c_preamble()
        if not cluster:
            return
        for index,server in cluster.items():
            status = await get_server_status(server.uri)
            if status != None:
                await stop_server(server.uri)
        await self.do_show_cluster()
    
    async def do_start_servers(self, hostname='127.0.0.1'):
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
        await self.do_show_cluster()
                
    async def do_stop_server(self, index):
        cluster,server,status = self.s_preamble(index)
        if not cluster:
            return
        if not status:
            print(f"Server {index} {server.uri} was already stopped")
        else:
            await stop_server(server.uri)
        await self.do_show_cluster()
        
    async def do_server_exit_cluster(self, index):
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
        await self.do_show_cluster()
        
        
if __name__ == "__main__":
    
    parser = argparse.ArgumentParser(description='Counters Raft Cluster Admin')

    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument('--discover', '-d', 
                        help='Filesystem location of where server working directories might be found')
    
    group.add_argument('--local_cluster', '-l', action="store_true",
                        help='Create or manage test cluster with all servers on this machine')
    
    parser.add_argument('--query_connect', '-q', 
                        help='Find cluster by quering provided address data in form host:port')

    parser.add_argument('--interactive', '-i', action="store_true",
                        help="Start interactive control after discovering cluster(s)")
    # Parse arguments
    args = parser.parse_args()

    
    asyncio.run(main(args))
