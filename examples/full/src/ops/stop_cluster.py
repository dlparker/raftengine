#!/usr/bin/env python
import asyncio
import argparse
import json
from pathlib import Path
import sys
src_dir = Path(__file__).parent.parent
logs_dir = Path(src_dir, 'logs')
sys.path.insert(0, str(logs_dir))
src_dir = Path(__file__).parent.parent
sys.path.insert(0, str(src_dir))

from admin_common import get_cluster_config, stop_server, get_server_status

async def main():
    parser = argparse.ArgumentParser(description="Counters Raft Cluster Stopper Tool")
    parser.add_argument('-u', '--uri', required=True, help="The URI of a running server in the cluster for discovery")
    args = parser.parse_args()

    config = await get_cluster_config(args.uri)
    uris = list(config.nodes.keys())
    tries = []
    for uri in uris:
        status = await get_server_status(uri)
        if status:
            print(f"calling stop on server {uri}")
            await stop_server(uri)
            tries.append(uri)
        else:
            print(f"server {uri} is not responding, not trying to stop it")
    await asyncio.sleep(0.01)
    for uri in tries:
        status = await get_server_status(uri)
        if status:
            print(f"server {uri} did not stop")
        else:
            print(f"server {uri}  stopped")
    

if __name__=="__main__":
    asyncio.run(main())
