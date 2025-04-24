import abc
from dataclasses import dataclass, field, asdict
from typing import Union, List, Optional
import logging
from copy import deepcopy
from raftengine.api.log_api import LogRec, LogAPI
from raftengine.api.types import ClusterConfig, NodeRec, ClusterSettings

logger = logging.getLogger(__name__)
class Records:

    def __init__(self):
        # log record indexes start at 1, per raftengine spec
        self.entries = []
        self.nodes = None
        self.pending_node = None
        self.cluster_settings = None

    @classmethod
    def from_json_dict(cls, jdict):
        res = cls()
        for entry_dict in jdict['entries']:
            res.entries.append(LogRec.from_dict(entry_dict))
        return res
    
    @property
    def index(self):
        return len(self.entries)
    
    def get_entry_at(self, index):
        if index < 1 or len(self.entries) == 0:
            return None
        return self.entries[index - 1]

    def get_last_entry(self):
        return self.get_entry_at(self.index)

    def insert_entry(self, rec: LogRec) -> LogRec:
        if rec.index > len(self.entries) + 1:
            raise Exception('cannont insert past last index')
        if rec.index == 0 or rec.index is None or rec.index == len(self.entries) + 1:
            self.entries.append(rec)
            rec.index = len(self.entries)
            return rec
        else:
            self.entries[rec.index-1] = rec

    def get_commit_index(self):
        for entry in self.entries[::-1]:
            if entry.committed:
                return entry.index
        return 0

    def get_applied_index(self):
        for entry in self.entries[::-1]:
            if entry.applied:
                return entry.index
        return 0

    def delete_all_from(self, index: int):
        if index == 0:
            self.entries = []
        else:
            self.entries = self.entries[:index-1]
        
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
    
class MemoryLog(LogAPI):

    def __init__(self):
        self.records = Records()
        self.term = 0
        self.voted_for = None

    @classmethod
    def from_json_dict(cls, jdict):
        res = cls()
        res.term =  jdict['term']
        res.records = Records.from_json_dict(jdict['records'])
        return res
    
    def start(self):
        pass
    
    async def get_term(self) -> Union[int, None]:
        return self.term
    
    async def set_term(self, value: int):
        self.term = value

    async def get_voted_for(self) -> Union[int, None]:
        return self.voted_for
    
    async def set_voted_for(self, value: int):
        self.voted_for = value

    async def incr_term(self):
        self.term += 1
        return self.term

    async def append(self, record: LogRec) -> None:
        save_rec = LogRec.from_dict(record.__dict__)
        self.records.insert_entry(save_rec)
        return_rec = LogRec.from_dict(save_rec.__dict__)
        logger.debug("new log record %s", return_rec.index)
        return return_rec
    
    async def append_multi(self, entries: List[LogRec]) -> None:
        # make copies for in memory list, and copy
        # the inserted ones to return to the caller
        # so they can see the index and can't break
        # our saved copy
        return_recs = []
        for entry in entries:
            return_recs.append(await self.append(entry))
        return return_recs

    async def replace(self, entry:LogRec) -> LogRec:
        if entry.index is None:
            raise Exception("api usage error, call append for new record")
        if entry.index < 1:
            raise Exception("api usage error, cannot insert at index less than 1")
        save_rec = LogRec.from_dict(entry.__dict__)
        self.records.insert_entry(save_rec)
        return LogRec.from_dict(save_rec.__dict__)

    async def update_and_commit(self, entry:LogRec) -> LogRec:
        entry.committed = True
        return await self.replace(entry)
    
    async def update_and_apply(self, entry:LogRec) -> LogRec:
        entry.applied = True
        return await self.replace(entry)
    
    async def read(self, index: Union[int, None] = None) -> Union[LogRec, None]:
        if index is None:
            rec = self.records.get_last_entry()
        else:
            if index < 1:
                raise Exception(f"cannot get index {index}, 1 is the first index")
            if index > self.records.index:
                return None
            rec = self.records.get_entry_at(index)
        if rec is None:
            return None
        return LogRec(**rec.__dict__)

    async def get_last_index(self):
        return self.records.index

    async def get_last_term(self):
        if self.records.index == 0:
            return 0
        rec = self.records.get_last_entry()
        return rec.term
    
    async def get_commit_index(self):
        return self.records.get_commit_index()

    async def get_applied_index(self):
        return self.records.get_applied_index()

    async def delete_all_from(self, index: int):
        return self.records.delete_all_from(index)

    async def save_cluster_config(self, config: ClusterConfig) -> None:
        return await self.records.save_cluster_config(config)
    
    async def get_cluster_config(self) -> Optional[ClusterConfig]:  
        return await self.records.get_cluster_config()

    def close(self):
        pass


        
    
