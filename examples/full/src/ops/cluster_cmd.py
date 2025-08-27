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
src_dir = Path(__file__).parent.parent
sys.path.insert(0, str(src_dir))
from raftengine.deck.log_control import LogController
log_controller = LogController.make_controller()
log_controller.set_default_level('warning')
from ops.cluster_mgr import ClusterMgr
from ops.command_loop import ClusterCLI

from ops.admin_common import (get_server_status, get_log_stats, send_heartbeats,
                              get_cluster_config, stop_server, take_snapshot, server_exit_cluster)
from ops.admin_common import ClusterBuilder, ClusterFinder



base_command_codes = ['list_clusters',]
selected_command_codes = ['cluster_status', 'start_servers', 'stop_cluster', 'send_heartbeats', 'new_server']
indexed_command_codes = ['stop_server', 'server_status', 'log_stats', 'take_snapshot','server_exit_cluster']
command_codes = base_command_codes + selected_command_codes + indexed_command_codes

async def main():
    
    parser = argparse.ArgumentParser(description='Counters Raft Cluster Admin')

    group = parser.add_mutually_exclusive_group(required=False)
    
    group.add_argument('--local-cluster', '-l', action="store_true",
                        help='Find a test cluster with servers all on this machine in --files-directory directory or /tmp')
    
    group.add_argument('--query-connect', '-q', 
                        help='Find cluster by quering provided address data in form host:port')

    group.add_argument('--create-local-cluster', action="store_true",
                        help="Create a test cluster with name '--name vaue' with servers all on this machine in --files-directory directory or /tmp")
    
    parser.add_argument('--files-directory', '-d', 
                        help='Filesystem location of where server working directories might be found')
    
    parser.add_argument('--name', '-n', 
                        help='Name of the cluster, either when finding or creating. Has no effect with --query_connect')

    parser.add_argument('--index', '-i', 
                        help='Index of server in name cluster for command (no effect on interactive ops)')

    parser.add_argument('--run-ops', choices=command_codes, action="append", default=[], 
                                help="Run the requested command an exit without starting interactive loop, can be used multiple times")
    
    parser.add_argument('-H', '--host-names', nargs='+', type=str, help='List of host names for cluster')
    
    parser.add_argument('-L', '--local-hosts', nargs='+', type=str, help='List of host names that address this host')

    parser.add_argument('-a', '--add-server', help="When given with '--run-ops new_server' will add a server at the" \
                        " given hostname, will be configured for local machine, started and told to join cluster")
    
    parser.add_argument('--json', '-j',  action="store_true",
                        help='Output results in json format, only applies to --run-ops commands')
    # Parse arguments
    args = parser.parse_args()
    

    clusters = None
    manager = ClusterMgr()
    if args.files_directory:
        root_dir = args.files_directory
        await manager.discover_cluster_files(search_dir=root_dir)
    else:
        root_dir = "/tmp"
    if args.name:
        target = args.name
    else:
        target = None
    if args.query_connect:
        host, port = args.query_connect.split(':')
        await manager.add_cluster(port=port, host=host)
    elif args.local_cluster:
        await manager.discover_cluster_files(search_dir=root_dir)
    elif args.create_local_cluster:
        if target is None:
            parser.error("You must provide a cluster name when creating one")
        await manager.create_local_cluster(target, directory=root_dir)
    elif args.run_ops != []:
        raise Exception("Cannot run commands without finding or creating a cluster first")

    cluster_cli = ClusterCLI(manager)
    if args.run_ops == []:
        await cluster_cli.run()
        return
    else:
        for cmd in args.run_ops:
            if cmd in selected_command_codes:
                if target is None:
                    run_ops_error(f"the {cmd} command requires a selected cluster")
            if cmd in indexed_command_codes:
                if target is None:
                    run_ops_error(f"the {cmd} command requires a selected cluster")
                if args.index is None:
                    run_ops_error(f"the {cmd} command requires a selected cluster and a server index")
    for op in args.run_ops:
        if op == "list_clusters":
            if args.json:
                print(await manager.list_clusters(return_json=True))
            else:
                await cluster_cli.do_list_clusters()
        elif op == "cluster_status":
            if args.json:
                print(await manager.cluster_status(return_json=True))
            else:
                await cluster_cli.do_cluster_status()
        elif op == "start_servers":
            if args.json:
                print(await manager.start_servers(return_json=True))
            else:
                await cluster_cli.do_start_servers()
        elif op == "stop_cluster":
            if args.json:
                print(await manager.stop_cluster(return_json=True))
            else:
                await cluster_cli.do_stop_cluster()
        elif op == "send_heartbeats":
            if args.json:
                print(await manager.send_heartbeats(return_json=True))
            else:
                await cluster_cli.do_send_heartbeats()
        elif op == "stop_server":
            if args.json:
                print(await manager.stop_server(args.index, return_json=True))
            else:
                await cluster_cli.do_stop_server(args.index)
        elif op == "server_status":
            if args.json:
                print(await manager.server_status(args.index, return_json=True))
            else:
                stats = await cluster_cli.do_server_status(args.index)
        elif op == "log_stats":
            if args.json:
                print(await manager.log_stats(args.index, return_json=True))
            else:
                stats = await cluster_cli.do_log_stats(args.index)
        elif op == "take_snapshot":
            if args.json:
                print(await manager.take_snapshot(args.index, return_json=True))
            else:
                stats = await cluster_cli.do_take_snapshot(args.index)
        elif op == "server_exit_cluster":
            if args.json:
                print(await manager.server_exit_cluster(args.index, return_json=True))
            else:
                stats = await cluster_cli.do_server_exit_cluster(args.index)
        elif op == "new_server":
            if args.json:
                print(await manager.new_server(args.add_server, return_json=True))
            else:
                stats = await cluster_cli.do_new_server(args.add_server)


        
