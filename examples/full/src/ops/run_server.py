#!/usr/bin/env python
import asyncio
import argparse
import shutil
import json
from pathlib import Path
from raftengine.api.deck_config import ClusterInitConfig, LocalConfig
from raftengine.deck.log_control import LogController
from raftengine_logs.sqlite_log import SqliteLog

log_controller = LogController.make_controller()
log_controller.set_default_level('warning')
log_controller.set_logger_level('Elections', 'info')

import sys
src_dir = Path(__file__).parent.parent
logs_dir = Path(src_dir, 'logs')
sys.path.insert(0, str(logs_dir))
src_dir = Path(__file__).parent.parent
sys.path.insert(0, str(src_dir))
from raft.raft_server import RaftServer

async def main(working_dir):
    config = None
    uri = None
    initial_config = None
    raft_log_file = Path(working_dir, "raftlog.db")
    if raft_log_file.exists():
        try:
            log = SqliteLog(self.raft_log_file)
            await log.start()
            config = await log.get_cluster_config()
            uri = await log.get_uri()
            await log.stop()
            working_dir = working_dir
        except Exception as e:
            print(f'unable to load config from existing log, looking for initial_config file {e}')
    if config is None:
        config_file_path = Path(working_dir, "initial_config.json")
        if not config_file_path.exists():
            raise Exception(f'cannot find "initial_config.json" in "{working_dir}"')
        try:
            with open(config_file_path, 'r') as f:
                config_data = json.load(f)
            initial_config = ClusterInitConfig(**config_data)
        except FileNotFoundError:
            print(f"Error: File '{config_file}' not found")
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in '{config_file}': {e}")
            sys.exit(1)
        uri_file_path = Path(working_dir, "uri_config.txt")
        with open(uri_file_path, 'r') as f:
                uri = f.read().strip("\n")
        if uri and uri not in initial_config.node_uris:
            raise Exception(f'Specified URI {uri} is not in {initial_config.node_uris}')
    local_config = LocalConfig(uri=uri, working_dir=working_dir)
    server = RaftServer(local_config, initial_config)
    try:
        await server.start()
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

    parser.add_argument('--working_dir', '-w', required=True,
                        help='Filesystem location of server working directory')
    parser.add_argument('--uri', '-u', 
                        help='URI for server, must match stored value if one exists in --working_dir')

    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument('-D', '--debug', action='store_true',
                       help="Set global logging level to debug")
    group.add_argument('-I', '--info', action='store_true',
                       help="Set global logging level to info")
    group.add_argument('-W', '--warning', action='store_true',
                       help="Set global logging level to warning")
    group.add_argument('-E', '--error', action='store_true',
                       help="Set global logging level to error, which is the default")
    # Parse arguments
    args = parser.parse_args()
    working_dir = Path(args.working_dir)
    if not working_dir.exists():
        raise Exception(f'specified working directory does not exist: {working_dir}')

    raft_log_file = Path(working_dir, "raftlog.db")
    config_file_path = Path(working_dir, "initial_config.json")
    if not raft_log_file.exists() and not config_file_path.exists():
        raise Exception(f'specified working directory contains neither raflog.db or initial_config.jason: {working_dir}')
    if args.warning:
        log_controller.set_default_level('warning')
    elif args.info:
        log_controller.set_default_level('info')
    if args.debug:
        log_controller.set_default_level('debug')
    asyncio.run(main(working_dir))
