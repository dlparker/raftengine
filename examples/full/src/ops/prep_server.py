#!/usr/bin/env python
import asyncio
import shutil
import argparse
import json
from pathlib import Path
from dataclasses import asdict
from raftengine_logs.sqlite_log import SqliteLog
from raftengine.api.deck_config import ClusterInitConfig, LocalConfig
import sys

async def main():

    parser = argparse.ArgumentParser(description="Create Counters Raft Server Cluster")
    
    parser.add_argument('config_file', 
                        help='JSON file containing cluster config captured from running cluster, or intitial config (see -i)')
    parser.add_argument('-n', '--nodes', nargs='+', type=str, help='List of host names that apply to this host, to identify local URIs')    
    parser.add_argument('--working_dir_root', '-w', required=True,
                        help='Filesystem location of server working directory parent directory')
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument('--reset-by-deleting-server-files', action="store_true",
                        help='Delete the server raft log file and config files. DANGEROUS, do this only if you are sure')
    group.add_argument('--check', '-c', action="store_true",
                        help='Check that the server log and config files match the config_file cluster')
    args = parser.parse_args()

    try:
        with open(args.config_file, 'r') as f:
            config_data = json.load(f)
    except FileNotFoundError:
        print(f"Error: File '{args.config_file}' not found")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in '{args.config_file}': {e}")
        sys.exit(1)

    this_host = ['127.0.0.1', 'localhost']
    if args.nodes:
        this_host.extend(args.nodes)
    
    if "node_uris" in config_data:
        init_config = ClusterInitConfig(**config_data)
        uris = init_config.node_uris
    else:
        settings = ClusterSettings(**config_data['settings'])
        nodes = []
        for uri,nr in config_data['nodes'].items():
            nodes.append(NodeRec(**nr))
        config = ClusterConfig(nodes, settings=settings)
        uris = list(config.node,keys())
        init_config = ClusterInitConfig(uris, **settings)
    local_uris =  []
    for uri in uris:
        host,port = uri.split('/')[-1].split(':')
        if host in this_host:
            local_uris.append(uri)
    if len(local_uris) == 0:
        print(f'No local servers in config file {args.config_file} (maybe use --nodes to identify local host name?)')
        return
    for uri in local_uris:
        host,port = uri.split('/')[-1].split(':')
        wd = Path(args.working_dir_root, f"counter_raft_server.{host}.{port}")
        if wd.exists():
            print(f"Working directory exists for {uri} at {wd}")
            if args.reset_by_deleting_server_files:
                print(f"Deleting {wd}")
                shutil.rmtree(wd)
            elif args.check:
                raft_log_file = Path(wd, "raftlog.db")
                if raft_log_file.exists():
                    print(f"checking log {raft_log_file}")
                    log = SqliteLog(raft_log_file)
                    await log.start()
                    saved_config = await log.get_cluster_config()
                    saved_uri = await log.get_uri()
                    await log.stop()
                    node_uris = list(saved_config.nodes.keys())
                    if uri != saved_uri:
                        raise Exception(f'Specified URI {uri} does not match log stored value {saved_uri}')
                    for uri in saved_config.nodes:
                        if uri not in node_uris:
                            raise Exception(f'Specified URI {uri} is not in {saved_config.nodes.keys()}')
        if not wd.exists():
            print(f"Creating directory for {uri} at {wd}")
            wd.mkdir(parents=True)
            init_config_file = Path(wd, 'initial_config.json')
            print(f"Saving init_config  at {init_config_file}")
            with open(init_config_file, 'w') as f:
                f.write(json.dumps(asdict(init_config), indent=2))
            uri_config_file = Path(wd, 'uri_config.txt')
            with open(uri_config_file, 'w') as f:
                f.write(uri)
    
if __name__=="__main__":
    asyncio.run(main())
