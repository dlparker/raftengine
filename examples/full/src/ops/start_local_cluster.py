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

from admin_common import find_local_clusters



async def main():
    
    parser = argparse.ArgumentParser(description="Counters Raft Server Local Cluster starter")
    parser.add_argument('-d', '--directory', required=True, help="The base directory for the working directories for the local cluster")
    
    args = parser.parse_args()
    clusters = await find_local_clusters(args.directory)
    
    for key in clusters.keys():
        if "127.0.0.1" in key:
            from pprint import pprint
            pprint(clusters[key])
            return
    print(f"Did not find any server config files for a local cluster (hostname=127.0.0.1) in {args.directory}")

if __name__=="__main__":
    asyncio.run(main())
