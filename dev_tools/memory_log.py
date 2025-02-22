import abc
from dataclasses import dataclass, field, asdict
from typing import Union, List, Optional
import logging
from raftengine.api.log_api import LogRec, LogAPI

class Records:

    def __init__(self):
        # log record indexes start at 1, per raftengine spec
        self.entries = []

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
        if rec.index == 0:
            self.entries.append(rec)
            rec.index = len(self.entries)
            return rec
        if rec.index == len(self.entries) + 1:
            self.entries.append(rec)
        if rec.index >= len(self.entries) + 1:
            raise Exception('cannont insert past last index')
        else:
            self.entries[rec.index-1] = rec
    
    def save_entry(self, rec: LogRec) -> LogRec:
        return self.insert_entry(rec)

    def get_commit_index(self):
        for entry in self.entries[::-1]:
            if entry.committed:
                return entry.index
        return 0

    def delete_all_from(self, index: int):
        self.entries = self.entries[:index-1]
        
        
    
class MemoryLog(LogAPI):

    def __init__(self):
        self.records = Records()
        self.term = 0
        self.server = None
        self.working_directory = None
        self.logger = logging.getLogger(__name__)
        
    async def start(self, server, working_directory):
        self.server = server
        self.working_directory = working_directory
    
    async def get_term(self) -> Union[int, None]:
        if not isinstance(self.term, int):
            breakpoint()
        return self.term
    
    async def set_term(self, value: int):
        if not isinstance(value, int):
            breakpoint()
        self.term = value

    async def incr_term(self):
        self.term += 1
        return self.term

    async def append(self, record: LogRec) -> None:
        save_rec = LogRec.from_dict(record.__dict__)
        self.records.insert_entry(save_rec)
        return_rec = LogRec.from_dict(save_rec.__dict__)
        self.logger.debug("new log record %s", return_rec.index)
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
        if entry.index == 0:
            raise Exception("api usage error, cannot insert at index 0")
        save_rec = LogRec.from_dict(entry.__dict__)
        self.records.insert_entry(save_rec)
        return LogRec.from_dict(save_rec.__dict__)

    async def update_and_commit(self, entry:LogRec) -> LogRec:
        entry.committed = True
        return await self.replace(entry)
    
    async def read(self, index: Union[int, None] = None) -> Union[LogRec, None]:
        if index is None:
            rec = self.records.get_last_entry()
        else:
            if index < 1:
                raise Exception(f"cannot get index {index}, not in records")
            if index > self.records.index:
                raise Exception(f"cannot get index {index}, not in records")
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

    async def delete_all_from(self, index: int):
        return self.records.delete_all_from(index)
        
    def close(self):
        pass


        
    
