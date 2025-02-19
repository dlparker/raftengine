from typing import Any, List
import json
from .base_message import BaseMessage
from raftengine.log.log_api import LogRec


class AppendEntriesMessage(BaseMessage):

    def __init__(self, sender:str, receiver:str, term:int, prevLogIndex:int, prevLogTerm:int,
                 entries:List[Any], commitIndex: int=0):
        BaseMessage.__init__(self, sender, receiver, term, prevLogIndex, prevLogTerm)
        self.code = "append_entries"
        self.entries = entries
        self.commitIndex = commitIndex
        self.entry_count = 0

    # Convenience method for programmers, normal operationss
    # encode by calling to_json
    def encode_entries(self):
        self.orig_entries = self.entries
        if len(self.entries) == 0:
            self.entries = "[]"
            self.entry_count = 0
            return
        if not isinstance(self.entries[0], LogRec):
            return
        self.entry_count = len(self.entries)
        self.orig_entries = self.entries
        self.entries = json.dumps(self.entries, default=lambda o:o.__dict__)
        
    # Convenience method for programmers, normal operationss
    # decode using from_dict classmethod
    def decode_entries(self):
        if len(self.entries) == 0:
            return
        if isinstance(self.entries[0], LogRec):
            return
        result = []
        for dic in json.loads(self.entries):
            result.append(LogRec.from_dict(dic))
        self.orig_entries = self.entries
        self.entries = result

    def to_json(self):
        # in case no one has decoded the entries yet
        self.deccode_entries()
        self.entries = json.dumps(self.entries, default=lambda o:o.__dict__)
        
    @classmethod
    def from_dict(cls, data):
        entries = []
        if isinstance(data['entries'], str):
            data['entries'] = json.loads(data['entries'])
        for obj in data['entries']:
            if isinstance(obj, LogRec):
                entries.append(obj)
            else:
                entries.append(LogRec.from_dict(obj))
        msg = cls(sender=data['sender'],
                  receiver=data['receiver'],
                  term=int(data['term']),
                  prevLogIndex=int(data['prevLogIndex']),
                  prevLogTerm=int(data['prevLogTerm']),
                  entries=entries,
                  commitIndex=int(data['commitIndex']),)
        return msg
    
    def __repr__(self):
        msg = super().__repr__()
        if hasattr(self,'orig_entries'):
            msg += f" e={len(self.orig_entries)} ci={self.commitIndex}"
        else:
            msg += f" e={len(self.entries)} ci={self.commitIndex}"
        return msg

class AppendResponseMessage(BaseMessage):

    code = "append_response"

    def __init__(self, sender:str, receiver:str, term:int, prevLogIndex:int, prevLogTerm:int,
                 recordIds: List[int], leaderId: str):
        BaseMessage.__init__(self, sender, receiver, term, prevLogIndex, prevLogTerm)
        self.leaderId = leaderId
        self.recordIds = recordIds


    def __repr__(self):
        msg = super().__repr__()
        msg += f" r={len(self.recordIds)} le={self.leaderId}"
        return msg
