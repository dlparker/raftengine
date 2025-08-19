#!/usr/bin/env python
import asyncio
import argparse
import json
from pathlib import Path
import sys
from raftengine.api.deck_config import ClusterInitConfig
from raftengine.api.types import ClusterConfig, NodeRec, ClusterSettings
src_dir = Path(__file__).parent.parent
logs_dir = Path(src_dir, 'logs')
sys.path.insert(0, str(logs_dir))
src_dir = Path(__file__).parent.parent
sys.path.insert(0, str(src_dir))

from admin_common import find_local_clusters, get_server_status, get_cluster_config

async def main():
    parser = argparse.ArgumentParser(description="Counters Raft Cluster Discovery Tool")
    parser.add_argument('-d', '--directory', required=True, help="The base directory for the working directories for the local cluster")
    args = parser.parse_args()

    clusters = await find_local_clusters(args.directory)

    for key,cluster in clusters.items():
        print("-"*120)
        if "127.0.0.1" in key:
            is_local = True
            print(f"cluster with key {key} is a local only cluster:")
        else:
            is_local = False
            print(f"cluster with key {key}:")
        uris = list(cluster.keys())
        uris.sort()
        for uri in uris:
            spec = cluster[uri]
            status = await get_server_status(uri)
            if status is not None:
                # we have contact, so we can get an up to date cluster config and query all the servers.
                print(f"local server {uri} running as pid = {status['pid']} in {status['working_dir']} with leader {status['leader_uri']}")
                config  = await get_cluster_config(uri)
                for n_uri, node in config.nodes.items():
                    if n_uri != uri:
                        ss = await get_server_status(n_uri)
                        if ss:
                            if n_uri in uris:
                                local = "local"
                            else:
                                local = "remote"
                            print(f"{local} server {n_uri} running as pid = {ss['pid']} in {ss['working_dir']} with leader {ss['leader_uri']}")
                        else:
                            print(f"server {n_uri} is not running")
                break
            else:
                print(f"server {uri} not running")
        print("-"*120)
            
    

if __name__=="__main__":
    asyncio.run(main())
