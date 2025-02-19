from typing import Any, List
import json
from .base_message import BaseMessage
from raftengine.api.log_api import LogRec


class AppendEntriesMessage(BaseMessage):

    code = "append_entries"
    
    def __init__(self, sender:str, receiver:str, term:int, prevLogIndex:int, prevLogTerm:int,
                 entries:List[Any], commitIndex: int=0):
        BaseMessage.__init__(self, sender, receiver, term, prevLogIndex, prevLogTerm)
        self.entries = entries
        self.commitIndex = commitIndex
        
    @classmethod
    def from_dict(cls, data):
        entries = []
        for obj in data['entries']:
            # this lets you used this as a copy function, not just for
            # fixup after json.loads
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
        msg += f" e={len(self.entries)} ci={self.commitIndex}"
        return msg

class AppendResponseMessage(BaseMessage):

    code = "append_response"

    def __init__(self, sender:str, receiver:str, term:int, prevLogIndex:int, prevLogTerm:int,
                 recordIds: List[int], leaderId: str):
        BaseMessage.__init__(self, sender, receiver, term, prevLogIndex, prevLogTerm)
        self.leaderId = leaderId
        self.recordIds = recordIds

    @classmethod
    def from_dict(cls, data):
        msg = cls(sender=data['sender'],
                  receiver=data['receiver'],
                  term=int(data['term']),
                  prevLogIndex=int(data['prevLogIndex']),
                  prevLogTerm=int(data['prevLogTerm']),
                  recordIds=data['recordIds'],
                  leaderId=data['leaderId'])
        return msg
        
    def __repr__(self):
        msg = super().__repr__()
        msg += f" r={len(self.recordIds)} le={self.leaderId}"
        return msg
