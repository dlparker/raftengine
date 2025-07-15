#!/usr/bin/env python
import asyncio
import sys
import os
import argparse
from pathlib import Path
import logging
from enum import StrEnum
from typing import Callable, Union
import importlib
from raftengine.api.deck_config import ClusterInitConfig, LocalConfig
from raftengine.deck.log_control import LogController
from raft_ops.raft_server import RaftServer
my_loggers = [('bank_demo', 'Demo raft integration banking app'),
              ('RaftServer', 'Server component that combines raft support for Raftengine library'),
              ('Pilot', 'Server component that implements PilotAPI'),]
log_control = LogController(my_loggers, default_level="warning")
logger = logging.getLogger('bank_demo')


class FileEventType(StrEnum):
    CREATED = "created"
    DELETED = "deleted"
    MODIFIED = "modified"

class FileWatcher:
    def __init__(self, path: Union[str, Path], callback: Callable[[Path, FileEventType], None], autodelete: bool = False):
        self.path = Path(path)
        self.callback = callback
        self.autodelete = autodelete
        self._last_modified = {}
        self._last_size = {}
        self._existing_files = set()
        self._running = False
        
    async def watch(self):
        """Monitor the path for file changes and call callback on events"""
        self._running = True
        
        # Initialize state
        if self.path.exists():
            if self.path.is_file():
                self._update_file_state(self.path)
                self._existing_files.add(self.path)
            elif self.path.is_dir():
                for file_path in self.path.rglob("*"):
                    if file_path.is_file():
                        self._update_file_state(file_path)
                        self._existing_files.add(file_path)
        
        while self._running:
            try:
                current_files = set()
                
                if self.path.exists():
                    if self.path.is_file():
                        current_files.add(self.path)
                        await self._check_file_changes(self.path)
                    elif self.path.is_dir():
                        for file_path in self.path.rglob("*"):
                            if file_path.is_file():
                                current_files.add(file_path)
                                await self._check_file_changes(file_path)
                
                # Check for new files
                new_files = current_files - self._existing_files
                for file_path in new_files:
                    self._update_file_state(file_path)
                    await self._invoke_callback(file_path, FileEventType.CREATED)
                
                # Check for deleted files
                deleted_files = self._existing_files - current_files
                for file_path in deleted_files:
                    self._remove_file_state(file_path)
                    await self._invoke_callback(file_path, FileEventType.DELETED)
                
                self._existing_files = current_files
                
            except Exception as e:
                logger.error(f"Error in FileWatcher: {e}")
            
            await asyncio.sleep(0.1)  # Check every 100ms
    
    async def _check_file_changes(self, file_path: Path):
        """Check if a file has been modified"""
        if not file_path.exists():
            return
            
        try:
            stat = file_path.stat()
            current_modified = stat.st_mtime
            current_size = stat.st_size
            
            if file_path in self._last_modified:
                if (current_modified != self._last_modified[file_path] or 
                    current_size != self._last_size[file_path]):
                    self._update_file_state(file_path)
                    await self._invoke_callback(file_path, FileEventType.MODIFIED)
            else:
                self._update_file_state(file_path)
        except OSError as e:
            logger.warning(f"Could not stat file {file_path}: {e}")
    
    def _update_file_state(self, file_path: Path):
        """Update cached file state"""
        try:
            stat = file_path.stat()
            self._last_modified[file_path] = stat.st_mtime
            self._last_size[file_path] = stat.st_size
        except OSError:
            pass
    
    def _remove_file_state(self, file_path: Path):
        """Remove cached file state"""
        self._last_modified.pop(file_path, None)
        self._last_size.pop(file_path, None)
    
    async def _invoke_callback(self, file_path: Path, event_type: FileEventType):
        """Invoke callback and optionally delete file"""
        await self.callback(file_path, event_type)
        if self.autodelete and file_path.exists():
            try:
                file_path.unlink()
                logger.info(f"Auto-deleted file: {file_path}")
            except OSError as e:
                logger.warning(f"Could not auto-delete file {file_path}: {e}")
    
    def stop(self):
        """Stop watching for file changes"""
        self._running = False


async def server_main(rpc_helper, uri, cluster_config, local_config, start_pause=False):
    path_root = Path(local_config.working_dir)
    if not path_root.exists():
        path_root.mkdir()
    db_path = Path(path_root, 'raft_log.db')
    raft_server = RaftServer(cluster_config, local_config, rpc_helper.rpc_client_maker)
    rpc_server = await rpc_helper.get_rpc_server(raft_server)
    
    # Write process ID to server.pid file
    pid_file = Path(local_config.working_dir, 'server.pid')
    with open(pid_file, 'w') as f:
        f.write(str(os.getpid()))
    logger.info(f"PID {os.getpid()} written to {pid_file}")
    
    # Start file watcher for server.stop file
    stop_file = Path(local_config.working_dir, 'server.stop')
    async def stop_detected(path: Path, event_type: FileEventType):
        nonlocal raft_server
        """Handle detection of server.stop file"""
        # User will fill in the actions they want here
        logger.info(f"Stop file detected: {path} ({event_type})")
        await raft_server.stop()
        await rpc_helper.stop_server_task()
    
    stop_watcher = FileWatcher(stop_file, stop_detected, autodelete=True)
    watcher_task = asyncio.create_task(stop_watcher.watch())
    logger.info(f"Started file watcher for {stop_file}")

    if start_pause:
        go_file = Path(local_config.working_dir, 'server.go')
        if go_file.exists():
            go_file.unlink()
        go_flag = False
        async def go_noted(path, event_type):
            nonlocal go_flag
            go_flag = True
        go_watcher = FileWatcher(go_file, go_noted, autodelete=True)
        go_watcher_task = asyncio.create_task(go_watcher.watch())
        print(f'Waiting for go file {go_file}', flush=True)
        while not go_file.exists():
            await asyncio.sleep(0.0001)
        
    
    await rpc_helper.start_server_task()
    await raft_server.start()
    logger.info(f"{uri} server started")
    for index,ouri in enumerate(cluster_config.node_uris):
        if ouri == uri and index == 0:
            async def coup():
                await asyncio.sleep(0.75)
                print("starting campain because index = 0")
                await raft_server.deck.start_campaign()
            asyncio.create_task(coup())
            
    while not raft_server.stopped:
        await asyncio.sleep(0.0001)
    
    logger.info("Raft server stopped")
    # Clean up file watcher
    stop_watcher.stop()
    watcher_task.cancel()
    try:
        await watcher_task
    except asyncio.CancelledError:
        pass
    
async def main_async(start_pause=True):
    """Main async function that can be called directly or from command line"""
    parser = argparse.ArgumentParser(
        description='Banking Raft Server Runner',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --transport grpc --base_port 8080
  %(prog)s  -t fastapi -p 8000

Available transports:
  aiozmq, grpc, fastapi, astream
        """
    )

    parser.add_argument(
        '-t', '--transport',
        required=True,
        help='Transport mechanism within the step'
    )
    
    parser.add_argument('-b', '--base_port', type=int, default=50050, help='Port number for first node (of 3) in cluster')
    parser.add_argument('-i', '--index', type=int, required=True, help='Index of node in cluster node list to start (0,1 or 2)')
    parser.add_argument('-s', '--slow_timeouts', action='store_true', help='Set raft timeout values to be extremely long')
    parser.add_argument('-w', '--startup_pause', action='store_true', help='Wait for server.go file before starting raft server')

    # Parse arguments
    args = parser.parse_args()

    # Get step and transport
    transport = args.transport
    
    # Validate combination
    valid_txs = ("astream", "aiozmq", "fastapi", "grpc")
    if transport not in valid_txs:
        raise
    if transport == "astream":
        from tx_astream.rpc_helper import RPCHelper
        base_port = args.base_port
    elif transport == "aiozmq":
        from tx_aiozmq.rpc_helper import RPCHelper
        base_port = args.base_port + 100
    elif transport == "fastapi":
        from tx_fastapi.rpc_helper import RPCHelper
        base_port = args.base_port + 200
    elif transport == "grpc":
        from tx_grpc.rpc_helper import RPCHelper
        base_port = args.base_port + 300
    else:
        raise Exception(f"invalid transport {transport}, try {valid_txs}")
    nodes = []
    for pnum in range(base_port, base_port + 3):
        nodes.append(f"{args.transport}://127.0.0.1:{pnum}")


    heartbeat_period=0.01
    election_timeout_min=0.150
    election_timeout_max=0.350
    if args.slow_timeouts:
        heartbeat_period=10000
        election_timeout_min=20000
        election_timeout_max=20001
    c_config = ClusterInitConfig(node_uris=nodes,
                                 heartbeat_period=heartbeat_period,
                                 election_timeout_min=election_timeout_min,
                                 election_timeout_max=election_timeout_max,
                                 use_pre_vote=False,
                                 use_check_quorum=True,
                                 max_entries_per_message=10,
                                 use_dynamic_config=False)
    uri = nodes[args.index]
    tmp = uri.split('/')
    host, port = tmp[-1].split(':')
    rpc_helper = RPCHelper(port)
    work_dir = Path('/tmp', f"raft_server.{args.transport}.{args.index}")
    if not work_dir.exists():
        work_dir.mkdir()
    local_config = LocalConfig(uri=uri, working_dir=work_dir)
    print(f"cluster nodes: {nodes}, starting {uri} with workdir={work_dir}")
    await server_main(rpc_helper, uri, c_config,  local_config, start_pause=args.startup_pause)

