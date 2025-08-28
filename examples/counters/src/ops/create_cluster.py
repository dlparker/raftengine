#!/usr/bin/env python
import asyncio
import shutil
import argparse
import json
from pathlib import Path
from pprint import pprint
import sys
src_dir = Path(__file__).parent.parent
sys.path.insert(0, str(src_dir))
from ops.admin_common import ClusterBuilder, ClusterServerConfig
        
async def main():

    parser = argparse.ArgumentParser(description="Create Counters Raft Server Cluster")
    
    parser.add_argument('-n', '--cluster-name', required=True, help='Name for the cluster (to allow multiple clusters)')
    parser.add_argument('-p', '--port', type=int, default=50090,
                        help='Port number for first node on each host, default 50090 for real cluster, 50100 for local only')
    parser.add_argument('-b', '--base-directory', type=str, default="/tmp",
                        help='Parent directory that will contain working directories for any local servers')
    parser.add_argument('-s', '--slow-timeouts', action='store_true',  help='Very long timeout values easing debug logging load')
    parser.add_argument('-f', '--force', action='store_true',  help='Force overwrite of existing config and db files')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-H', '--host-names', nargs='+', type=str, help='List of host names to run nodes')    
    group.add_argument('-a', '--all-local', action='store_true',  help='All servers on this host')
    args = parser.parse_args()

    cb = ClusterBuilder()
    if args.all_local:
        if args.port == 50090:
            port = 50100
        else:
            port = args.port
        local_servers = cb.build_local(name=args.cluster_name, base_port=port, slow_timeouts=args.slow_timeouts)
        cb.setup_local_files(local_servers, args.base_directory, overwrite=args.force)
        pprint(local_servers)
    else:
        all_servers = cb.build(name=args.cluster_name, base_port=args.port, hosts=args.nodes)
        cb.setup_local_files(all_servers, args.base_directory, local_host_names=['frame2',], overwrite=args.force)
        pprint(all_servers)
    
    
if __name__=="__main__":
    asyncio.run(main())
