#!/usr/bin/env python
import asyncio
import argparse
import shutil
import json
from pathlib import Path
from dataclasses import asdict
from raftengine.api.deck_config import ClusterInitConfig, LocalConfig
from raftengine.deck.log_control import LogController
from raftengine_logs.sqlite_log import SqliteLog

log_controller = LogController.make_controller()
log_controller.set_default_level('warning')
log_controller.set_logger_level('Elections', 'info')

import sys
src_dir = Path(__file__).parent.parent
sys.path.insert(0, str(src_dir))
from raft.raft_server import RaftServer
from admin_common import ClusterServerConfig, get_cluster_config, get_server_status

def save_config(uri, working_dir, config, status):
    cluster_name = status['cluster_name']
    uris = list(config.nodes.keys())
    cdict = dict(node_uris=uris)
    cdict.update(asdict(config.settings))
    initial_config = ClusterInitConfig(**cdict)
    if "127.0.0.1" in str(uris):
        all_local = True
    else:
        all_local = False
    csc = ClusterServerConfig(uri, str(working_dir), cluster_name, initial_config, all_local=all_local)
    with open(Path(working_dir, 'server_config.json'), 'w') as f:
        f.write(json.dumps(asdict(csc), indent=2))
    return csc
    
async def joiner(base_dir, join_uri, cluster_uri):
    config = await get_cluster_config(cluster_uri)
    if join_uri in config.nodes:
        raise Exception(f"URI {join_uri} is already part of cluster")
    status = await get_server_status(cluster_uri)
    host,port = join_uri.split('/')[-1].split(':')
    wd = Path(base_dir, f"full_raft_server.{host}.{port}")
    if not wd.exists():
        wd.mkdir(parents=True)
    csc = save_config(join_uri, wd, config, status)
    return csc, status['leader_uri']
    
async def starter(working_dir):
    if not working_dir.exists():
        raise Exception(f'specified working directory does not exist: {working_dir}')
    config_file_path = Path(working_dir, "server_config.json")
    if not config_file_path.exists():
        raise Exception(f'specified working directory does not contain server_config.json: {working_dir}')
    with open(config_file_path, 'r') as f:
        config_data = json.load(f)
        config = ClusterServerConfig.from_dict(config_data)
    return config
    
async def main(working_dir, join_uri=None, cluster_uri=None):
    
    if join_uri:
        config,leader_uri = await joiner(working_dir, join_uri, cluster_uri)
    else:
        config = await starter(working_dir)
    local_config = LocalConfig(uri=config.uri, working_dir=config.working_dir)
    server = RaftServer(local_config, config.initial_config, config.cluster_name)
    if join_uri:
        await server.start_and_join(leader_uri)
    else:
        await server.start()
    # now save up to date config
    config = await server.log.get_cluster_config()
    status = await server.direct_commander.get_status()
    save_config(server.uri, working_dir, config, status)
    try:
        while not server.stopped:
            try:
                await asyncio.sleep(0.01)
            except asyncio.CancelledError:
                await server.stop()
                break
    except KeyboardInterrupt:
        print("Cntl-c, trying to stop server", flush=True)
        await server.stop()
        start_time = time.time() 
        while not server.stopped and time.time() - start_time < 2.0:
            await asyncio.sleep(0.01)
        if not server.stopped:
            raise Exception('could not stop server in two seconds')
        
if __name__=="__main__":
    import uvloop;
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    
    parser = argparse.ArgumentParser(description='Counters Raft Server')

    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument('--working_dir', '-w', 
                        help='Filesystem location of server working directory')
    group.add_argument('--base_dir', '-b', 
                        help='Filesystem location of where server working directory should be created')
    
    parser.add_argument('--join_uri', '-j', 
                        help='Server should join running cluster as provided uri')
    parser.add_argument('--cluster_uri', '-c', 
                        help='Server should join running cluster by contacting provided uri')

    group2 = parser.add_mutually_exclusive_group(required=False)
    group2.add_argument('-D', '--debug', action='store_true',
                       help="Set global logging level to debug")
    group2.add_argument('-I', '--info', action='store_true',
                       help="Set global logging level to info")
    group2.add_argument('-W', '--warning', action='store_true',
                       help="Set global logging level to warning")
    group2.add_argument('-E', '--error', action='store_true',
                       help="Set global logging level to error, which is the default")
    # Parse arguments
    args = parser.parse_args()

    if args.join_uri:
        if not args.cluster_uri:
            parser.error("must supply cluster uri with join uri")
        if args.base_dir is None:
            parser.error("must supply --base-dir with join uri")
        working_dir = Path(args.base_dir)
    elif args.cluster_uri:
        parser.error("must supply cluster uri with join uri")
    else:
        if args.working_dir is None:
            parser.error("must supply working directory if not using --join_uri")
        working_dir = Path(args.working_dir)
    if args.warning:
        log_controller.set_default_level('warning')
    elif args.info:
        log_controller.set_default_level('info')
    if args.debug:
        log_controller.set_default_level('debug')
    asyncio.run(main(working_dir, args.join_uri, args.cluster_uri))
