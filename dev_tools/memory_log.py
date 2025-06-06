import abc
from dataclasses import dataclass, field, asdict
from typing import Union, List, Optional
import logging
from copy import deepcopy
from raftengine.api.log_api import LogRec, LogAPI
from raftengine.api.snapshot_api import SnapShot
from raftengine.api.types import ClusterConfig, NodeRec, ClusterSettings

logger = logging.getLogger(__name__)

class MemoryLog(LogAPI):
    
    def __init__(self):
        self.first_index = 0
        self.last_index = 0
        self.last_term = 0
        self.term = 0
        self.entries = {}
        self.voted_for = None
        self.snapshot = None
        self.nodes = None
        self.pending_node = None
        self.cluster_settings = None

    def close(self):
        self.first_index = 0
        self.last_index = 0
        self.last_term = 0
        self.term = 0
        self.entries = {}
        self.voted_for = None
        self.snapshot = None
        self.nodes = None
        self.pending_node = None
        self.cluster_settings = None
        
    def insert_entry(self, rec: LogRec) -> LogRec:
        if rec.index > self.last_index + 1:
            raise Exception('cannont insert past last index')
        if rec.index == 0 or rec.index is None:
            rec.index = self.last_index + 1
        self.entries[rec.index] = rec
        self.last_index = max(rec.index, self.last_index)
        self.last_term = max(rec.term, self.last_term)
        if self.first_index == 0 or self.first_index is None:
            self.first_index = rec.index
        if self.last_index <= rec.index:
            # It is possible for the last record to be re-written
            # with a new term, and we can't tell that from
            # an update to record commit or apply flag, so
            # we'll assume that the term needs to update
            self.last_index = rec.index
            self.last_term = rec.term
        return rec
            
    def get_entry_at(self, index):
        return self.entries.get(index, None)

    def get_last_entry(self):
        return self.get_entry_at(self.last_index)

    async def delete_ending_with(self, index: int):
        if index == self.last_index:
            self.entries = {}
        else:
            keys = list(self.entries.keys())
            keys.sort()
            for rindex in keys:
                if rindex <= index:
                    del self.entries[rindex]
        if len(self.entries) == 0:
            self.first_index = None
            if self.snapshot:
                self.last_index = self.snapshot.last_index
                self.last_term = self.snapshot.last_term
            else:
                self.last_index = 0
                self.last_term = 0
        else:
            self.first_index = index + 1

    # BEGIN API METHODS
    def start(self):
        pass

    async def get_term(self) -> Union[int, None]:
        return self.term
    
    async def set_term(self, value: int):
        self.term = value

    async def incr_term(self):
        self.term += 1
        return self.term

    async def get_voted_for(self) -> Union[int, None]:
        return self.voted_for
    
    async def set_voted_for(self, value: int):
        self.voted_for = value

    async def get_last_index(self):
        return self.last_index

    async def get_first_index(self):
        return self.first_index
    
    async def get_last_term(self):
        return self.last_term
    
    async def get_commit_index(self):
        keys = list(self.entries.keys())
        keys.sort()
        for rindex in keys[::-1]:
            entry = self.entries[rindex]
            if entry.committed:
                return entry.index
        if self.snapshot:
            return self.snapshot.last_index
        return 0

    async def get_applied_index(self):
        keys = list(self.entries.keys())
        keys.sort()
        for rindex in keys[::-1]:
            entry = self.entries[rindex]
            if entry.applied:
                return entry.index
        if self.snapshot:
            return self.snapshot.last_index
        return 0
    
    async def append_multi(self, entries: List[LogRec]) -> None:
        # make copies for in memory list, and copy
        # the inserted ones to return to the caller
        # so they can see the index and can't break
        # our saved copy
        return_recs = []
        for entry in entries:
            return_recs.append(await self.append(entry))
        return return_recs
    
    async def append(self, record: LogRec) -> None:
        save_rec = LogRec.from_dict(record.__dict__)
        self.insert_entry(save_rec)
        return_rec = LogRec.from_dict(save_rec.__dict__)
        logger.debug("new log record %s", return_rec.index)
        return return_rec
    
    async def replace(self, entry:LogRec) -> LogRec:
        if entry.index is None:
            raise Exception("api usage error, call append for new record")
        if entry.index < 1:
            raise Exception("api usage error, cannot insert at index less than 1")
        save_rec = LogRec.from_dict(entry.__dict__)
        self.insert_entry(save_rec)
        return LogRec.from_dict(save_rec.__dict__)

    async def update_and_commit(self, entry:LogRec) -> LogRec:
        entry.committed = True
        return await self.replace(entry)

    async def update_and_apply(self, entry:LogRec) -> LogRec:
        entry.applied = True
        return await self.replace(entry)
    
    async def read(self, index: Union[int, None] = None) -> Union[LogRec, None]:
        if index is None:
            rec = self.get_last_entry()
        else:
            if index < 1:
                raise Exception(f"cannot get index {index}, 1 is the first index")
            if index > self.last_index:
                return None
            if self.first_index is None:
                return None
            if index < self.first_index:
                return None
            rec = self.get_entry_at(index)
        if rec is None:
            return None
        return LogRec(**rec.__dict__)
    
    async def delete_all_from(self, index: int):
        if index == 0:
            self.entries = {}
            self.first_entry = 0
            if self.snapshot:
                self.last_index = self.snapshot.last_index
                self.last_term = self.snapshot.last_term
            else:
                self.last_index = 0
                self.last_term = 0
        else:
            keys = list(self.entries.keys())
            keys.sort()
            for rindex in keys[::-1]:
                if rindex >= index:
                    del self.entries[rindex]
            keys = list(self.entries.keys())
            keys.sort()
            if len(keys) == 0:
                self.first_index = self.last_index = self.term = 0
                return
            self.first_index = keys[0]
            self.last_index = keys[-1]
            rec = self.entries[self.last_index]
            self.last_term = rec.term

    async def save_cluster_config(self, config: ClusterConfig) -> None:
        self.nodes = deepcopy(config.nodes)
        self.pending_node = deepcopy(config.pending_node)
        self.cluster_settings = deepcopy(config.settings)
        return ClusterConfig(nodes=deepcopy(self.nodes),
                             pending_node=deepcopy(self.pending_node),
                             settings=deepcopy(self.cluster_settings))
    
    async def get_cluster_config(self):
        if self.nodes is None:
            return None
        return ClusterConfig(nodes=deepcopy(self.nodes),
                             pending_node=deepcopy(self.pending_node),
                             settings=deepcopy(self.cluster_settings))
    
    async def install_snapshot(self, snapshot:SnapShot):
        self.snapshot = snapshot
        end_index = self.snapshot.last_index
        await self.delete_ending_with(end_index)
        self.last_term = max(self.snapshot.last_term, self.last_term)
        self.last_index = max(self.snapshot.last_index, self.last_index)
        if self.last_index > self.snapshot.last_index:
            self.first_index = self.snapshot.last_index + 1
        else:
            self.first_index = None
    
    async def get_snapshot(self):
        return self.snapshot
    

        
    
