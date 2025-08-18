#!/usr/bin/env python
import asyncio
import argparse
import json
from pathlib import Path
from subprocess import Popen
import sys
from raftengine.api.deck_config import ClusterInitConfig
from raftengine.api.types import ClusterConfig, NodeRec, ClusterSettings
src_dir = Path(__file__).parent.parent
logs_dir = Path(src_dir, 'logs')
sys.path.insert(0, str(logs_dir))
src_dir = Path(__file__).parent.parent
sys.path.insert(0, str(src_dir))

from admin_common import find_local_clusters, get_server_status


async def main():
    
    parser = argparse.ArgumentParser(description="Counters Raft Server Local Cluster starter")
    parser.add_argument('-d', '--directory', required=True, help="The base directory for the working directories for the local cluster")
    
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument('-D', '--debug', action='store_true',
                       help="Set global logging level to debug")
    group.add_argument('-I', '--info', action='store_true',
                       help="Set global logging level to info")
    group.add_argument('-W', '--warning', action='store_true',
                       help="Set global logging level to warning")
    group.add_argument('-E', '--error', action='store_true',
                       help="Set global logging level to error, which is the default")

    args = parser.parse_args()
    logging_level = 'error'
    if args.warning:
        logging_level = 'warning'
    if args.info:
        logging_level = 'info'
    if args.debug:
        logging_level = 'debug'
    clusters = await find_local_clusters(args.directory)

    local = None
    for key in clusters.keys():
        if "127.0.0.1" in key:
            local = clusters[key] 
            break
    if local is None:
        print(f"Did not find any server config files for a local cluster (hostname=127.0.0.1) in {args.directory}")
    for uri,spec in local.items():
        status = await get_server_status(uri)
        if status is not None:
            print(f"server {uri} not running as pid = {status['pid']} in {status['working_dir']} with leader {status['leader_uri']}")
        else:
            print(f"server {uri} not running, starting")
            this_dir = Path(__file__).parent
            working_dir = spec['working_dir']
            sfile = Path(this_dir, 'run_server.py')
            cmd = [str(sfile), "-w", working_dir, ]
            if logging_level == "warning":
                cmd.append("-W")
            elif logging_level == "info":
                cmd.append("-I")
            elif logging_level == "debug":
                cmd.append("-D")
            stdout_file = Path(working_dir,'server.stdout')
            stderr_file = Path(working_dir,'server.stderr')
            print(cmd)
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
            
    

if __name__=="__main__":
    asyncio.run(main())
