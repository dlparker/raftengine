#!/usr/bin/env python
import asyncio
import argparse
import sys
import os
from pathlib import Path
import logging
from enum import StrEnum
from typing import Callable, Union
from raftengine.deck.log_control import LogController
top_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(top_dir))
from src.raft.raft_components.pilot import DeckHand
from src.raft.raft_components.sqlite_log import SqliteLog
from src.raft.raft_components.raft_server import RaftServer
from src.raft_prep.transports.grpc.client import get_grpc_client

my_loggers = [('bank_demo', 'Demo raft integration banking app'),]
log_control = LogController(my_loggers, default_level="info")
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


async def server_main(uri, cluster_config, local_config):
    path_root = Path(local_config.working_dir)
    if not path_root.exists():
        path_root.mkdir()
    db_path = Path(path_root, 'raft_log.db')
    log = SqliteLog(db_path)
    log.start()
    await log.get_last_index()
    tmp = uri.split("/")  # Fixed: was 'url', now 'target_uri'
    transport = tmp[0].strip(':')
    if transport == "grpc":
        def client_maker(target_uri):
            tmp = target_uri.split("/")  # Fixed: was 'url', now 'target_uri'
            if tmp[0].strip(':') != "grpc":
                raise Exception(f'Misconfigure, should be grpc, not {tmp[0]}')
            host, port = tmp[-1].split(":")
            return get_grpc_client(host, int(port))
    else:
        raise Exception(f'no code for transport {transport}')
    
    server = RaftServer()
    deckhand = DeckHand(server, log, client_maker, cluster_config, local_config)
    server.set_deckhand(deckhand)
    await deckhand.start()
    logger.info(f"{uri} deck started")
    
    # Write process ID to server.pid file
    pid_file = Path(local_config.working_dir, 'server.pid')
    with open(pid_file, 'w') as f:
        f.write(str(os.getpid()))
    logger.info(f"PID {os.getpid()} written to {pid_file}")
    
    # Start file watcher for server.stop file
    stop_file = Path(local_config.working_dir, 'server.stop')
    async def stop_detected(path: Path, event_type: FileEventType):
        nonlocal deckhand
        """Handle detection of server.stop file"""
        # User will fill in the actions they want here
        logger.info(f"Stop file detected: {path} ({event_type})")
        await deckhand.stop()
    
    file_watcher = FileWatcher(stop_file, stop_detected, autodelete=True)
    watcher_task = asyncio.create_task(file_watcher.watch())
    logger.info(f"Started file watcher for {stop_file}")
    
    while not deckhand.deck.stopped:
        await asyncio.sleep(0.0001)
    
    logger.info("Deck (and deckhand) stopped")
    # Clean up file watcher
    file_watcher.stop()
    watcher_task.cancel()
    try:
        await watcher_task
    except asyncio.CancelledError:
        pass
    
