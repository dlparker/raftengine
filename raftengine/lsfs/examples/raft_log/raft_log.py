#!/usr/bin/env python3

import sys
import os
import asyncio
import json
from typing import Union, List, Optional

# Add src to path for imports
src_path = os.path.join(os.path.dirname(__file__), '..', '..', 'src')
sys.path.insert(0, src_path)

from block_writer import BlockWriter
from recorder import Recorder
from block_reader import BlockReader

# Import the API definitions
from log_api import LogAPI, LogRec, RecordCode
from raft_types import ClusterConfig
from snapshot_api import SnapShot

class LSFSRaftLog(LogAPI):
    # Record type codes for LSFS storage
    LOG_RECORD_TYPE = 1
    METADATA_TYPE = 2
    CLUSTER_CONFIG_TYPE = 3
    SNAPSHOT_TYPE = 4
    
    def __init__(self):
        self.working_directory = None
        self.log_file = None
        self.metadata_file = None
        self.recorder = None
        self.reader = None
        self.metadata_recorder = None
        self.metadata_reader = None
        
        # In-memory state
        self.current_term = 0
        self.voted_for = None
        self.commit_index = 0
        self.applied_index = 0
        self.broken = False
        self.cluster_config = None
        self.snapshot = None
        
        # Log record cache
        self.log_records = {}  # index -> LogRec
        self.first_index = 0
        self.last_index = -1
        
    async def start(self, working_directory: os.PathLike):
        self.working_directory = working_directory
        os.makedirs(working_directory, exist_ok=True)
        
        self.log_file = os.path.join(working_directory, "raft.log")
        self.metadata_file = os.path.join(working_directory, "raft.meta")
        
        # Initialize readers to load existing data
        await self._load_existing_data()
        
    async def _load_existing_data(self):
        # Load metadata if exists
        if os.path.exists(self.metadata_file):
            self.metadata_reader = BlockReader(self.metadata_file)
            await self.metadata_reader.open()
            await self._load_metadata()
            
        # Load log records if exists
        if os.path.exists(self.log_file):
            self.reader = BlockReader(self.log_file)
            await self.reader.open()
            await self._load_log_records()
            
    async def _load_metadata(self):
        if not self.metadata_reader:
            return
            
        # Load various metadata records
        for i in range(self.metadata_reader.first_record_index or 0, 
                      (self.metadata_reader.last_record_index or -1) + 1):
            data_bytes, record_type = await self.metadata_reader.get_record(i)
            if data_bytes:
                metadata = json.loads(data_bytes.decode('utf-8'))
                
                if metadata['type'] == 'term':
                    self.current_term = metadata['value']
                elif metadata['type'] == 'voted_for':
                    self.voted_for = metadata['value']
                elif metadata['type'] == 'commit_index':
                    self.commit_index = metadata['value']
                elif metadata['type'] == 'applied_index':
                    self.applied_index = metadata['value']
                elif metadata['type'] == 'cluster_config':
                    self.cluster_config = ClusterConfig(**metadata['value'])
                elif metadata['type'] == 'snapshot':
                    self.snapshot = SnapShot(**metadata['value'])
                    
    async def _load_log_records(self):
        if not self.reader:
            return
            
        self.log_records = {}
        
        if self.reader.first_record_index is not None:
            self.first_index = self.reader.first_record_index
            self.last_index = self.reader.last_record_index
            
            for i in range(self.first_index, self.last_index + 1):
                data_bytes, record_type = await self.reader.get_record(i)
                if data_bytes:
                    record_data = json.loads(data_bytes.decode('utf-8'))
                    log_rec = LogRec.from_dict(record_data)
                    self.log_records[log_rec.index] = log_rec
                    
    async def _save_metadata(self, metadata_type: str, value):
        if not self.metadata_recorder:
            block_writer = BlockWriter(self.metadata_file)
            self.metadata_recorder = Recorder(block_writer)
            
        metadata = {
            'type': metadata_type,
            'value': value
        }
        
        data_bytes = json.dumps(metadata).encode('utf-8')
        await self.metadata_recorder.record(data_bytes, self.METADATA_TYPE)
        
    async def set_broken(self) -> None:
        self.broken = True
        
    async def set_fixed(self) -> None:
        self.broken = False
        
    async def get_broken(self) -> bool:
        return self.broken
        
    async def get_term(self) -> int:
        return self.current_term
        
    async def set_term(self, value: int):
        self.current_term = value
        await self._save_metadata('term', value)
        
    async def incr_term(self) -> int:
        self.current_term += 1
        await self._save_metadata('term', self.current_term)
        return self.current_term
        
    async def get_voted_for(self) -> str:
        return self.voted_for
        
    async def set_voted_for(self, value: str):
        self.voted_for = value
        await self._save_metadata('voted_for', value)
        
    async def get_last_index(self) -> int:
        return self.last_index
        
    async def get_first_index(self) -> int:
        return self.first_index
        
    async def get_last_term(self) -> int:
        if self.last_index >= 0 and self.last_index in self.log_records:
            return self.log_records[self.last_index].term
        return 0
        
    async def get_commit_index(self) -> int:
        return self.commit_index
        
    async def get_applied_index(self) -> int:
        return self.applied_index
        
    async def append_multi(self, entries: List[LogRec]):
        for entry in entries:
            await self.append(entry)
            
    async def append(self, record: LogRec):
        if not self.recorder:
            block_writer = BlockWriter(self.log_file)
            self.recorder = Recorder(block_writer)
            
        # Set the index for the new record
        record.index = self.last_index + 1
        self.last_index = record.index
        
        if self.first_index == 0 and self.last_index == 0:
            self.first_index = 0
            
        # Store in memory cache
        self.log_records[record.index] = record
        
        # Serialize and store to LSFS
        record_data = {
            'index': record.index,
            'term': record.term,
            'command': record.command,
            'result': record.result,
            'error': record.error,
            'code': str(record.code),
            'serial': record.serial,
            'leader_id': record.leader_id,
            'committed': record.committed,
            'applied': record.applied
        }
        
        data_bytes = json.dumps(record_data).encode('utf-8')
        await self.recorder.record(data_bytes, self.LOG_RECORD_TYPE)
        
    def replace(self, entry: LogRec) -> LogRec:
        if entry.index in self.log_records:
            old_entry = self.log_records[entry.index]
            self.log_records[entry.index] = entry
            return old_entry
        return None
        
    def update_and_commit(self, entry: LogRec) -> LogRec:
        if entry.index in self.log_records:
            self.log_records[entry.index].committed = True
            self.commit_index = max(self.commit_index, entry.index)
            return self.log_records[entry.index]
        return None
        
    def update_and_apply(self, entry: LogRec) -> LogRec:
        if entry.index in self.log_records:
            self.log_records[entry.index].applied = True
            self.applied_index = max(self.applied_index, entry.index)
            return self.log_records[entry.index]
        return None
        
    async def read(self, index: Union[int, None] = None) -> Union[LogRec, None]:
        if index is None:
            index = self.last_index
            
        return self.log_records.get(index)
        
    async def delete_all_from(self, index: int) -> LogRec:
        # Remove all records from index onwards
        last_deleted = None
        
        indices_to_delete = [i for i in self.log_records.keys() if i >= index]
        for i in indices_to_delete:
            last_deleted = self.log_records.pop(i)
            
        if indices_to_delete:
            self.last_index = max([i for i in self.log_records.keys()], default=-1)
            
        return last_deleted
        
    async def save_cluster_config(self, config: ClusterConfig) -> None:
        self.cluster_config = config
        config_data = {
            'nodes': {k: {'uri': v.uri, 'is_adding': v.is_adding, 'is_removing': v.is_removing} 
                     for k, v in config.nodes.items()},
            'pending_node': ({'uri': config.pending_node.uri, 
                            'is_adding': config.pending_node.is_adding,
                            'is_removing': config.pending_node.is_removing} 
                           if config.pending_node else None),
            'settings': {
                'heartbeat_period': config.settings.heartbeat_period,
                'election_timeout_min': config.settings.election_timeout_min,
                'election_timeout_max': config.settings.election_timeout_max,
                'max_entries_per_message': config.settings.max_entries_per_message,
                'use_pre_vote': config.settings.use_pre_vote,
                'use_check_quorum': config.settings.use_check_quorum,
                'use_dynamic_config': config.settings.use_dynamic_config,
                'commands_idempotent': config.settings.commands_idempotent
            }
        }
        await self._save_metadata('cluster_config', config_data)
        
    async def get_cluster_config(self) -> Optional[ClusterConfig]:
        return self.cluster_config
        
    async def install_snapshot(self, snapshot: SnapShot) -> None:
        self.snapshot = snapshot
        snapshot_data = {
            'index': snapshot.index,
            'term': snapshot.term
        }
        await self._save_metadata('snapshot', snapshot_data)
        
    async def get_snapshot(self) -> Optional[SnapShot]:
        return self.snapshot
        
    async def close(self):
        if self.recorder:
            await self.recorder.block_writer.close()
        if self.reader:
            await self.reader.close()
        if self.metadata_recorder:
            await self.metadata_recorder.block_writer.close()
        if self.metadata_reader:
            await self.metadata_reader.close()

async def demo():
    print("LSFS Raft Log API Demo")
    print("=" * 40)
    
    # Create temp directory for demo
    working_dir = "/tmp/raft_demo"
    if os.path.exists(working_dir):
        import shutil
        shutil.rmtree(working_dir)
    
    raft_log = LSFSRaftLog()
    await raft_log.start(working_dir)
    
    print(f"Started log in: {working_dir}")
    print(f"Initial term: {await raft_log.get_term()}")
    print(f"Initial last index: {await raft_log.get_last_index()}")
    
    # Set term and voted_for
    await raft_log.set_term(1)
    await raft_log.set_voted_for("server1")
    
    # Append some log entries
    print("\nAppending log entries...")
    
    entry1 = LogRec(term=1, command="SET x=10", code=RecordCode.client_command)
    await raft_log.append(entry1)
    
    entry2 = LogRec(term=1, command="SET y=20", code=RecordCode.client_command)
    await raft_log.append(entry2)
    
    entry3 = LogRec(term=2, command="DELETE x", code=RecordCode.client_command)
    await raft_log.append(entry3)
    
    print(f"Last index after appends: {await raft_log.get_last_index()}")
    print(f"Last term: {await raft_log.get_last_term()}")
    
    # Read back entries
    print("\nReading entries:")
    for i in range(await raft_log.get_first_index(), await raft_log.get_last_index() + 1):
        entry = await raft_log.read(i)
        if entry:
            print(f"  Index {i}: term={entry.term}, command='{entry.command}', code={entry.code}")
    
    await raft_log.close()
    print(f"\nDemo complete. Files in: {working_dir}")

if __name__ == "__main__":
    asyncio.run(demo())