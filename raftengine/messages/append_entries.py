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
        copy_of = dict(data)
        del copy_of['code']
        copy_of['entries'] = entries
        msg = cls(**copy_of)
        return msg
    
    def __repr__(self):
        msg = super().__repr__()
        msg += f" e={len(self.entries)} ci={self.commitIndex}"
        return msg

class AppendResponseMessage(BaseMessage):

    code = "append_response"

    def __init__(self, sender:str, receiver:str, term:int, prevLogIndex:int, prevLogTerm:int,  maxIndex: int,
                 success: bool, leaderId: str):
        BaseMessage.__init__(self, sender, receiver, term, prevLogIndex, prevLogTerm)
        self.leaderId = leaderId
        self.success = success
        self.maxIndex = maxIndex

    @classmethod
    def from_dict(cls, data):
        copy_of = dict(data)
        del copy_of['code']
        msg = cls(**copy_of)
        return msg
        
    def __repr__(self):
        msg = super().__repr__()
        msg += f" s={self.success} mi={self.maxIndex} le={self.leaderId}"
        return msg
