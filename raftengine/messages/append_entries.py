from typing import Any, List
import json
from .base_message import BaseMessage
from raftengine.messages.log_msg import LogMessage
from raftengine.api.log_api import LogRec


class AppendEntriesMessage(LogMessage):

    code = "append_entries"
    
    def __init__(self, sender:str, receiver:str, term:int, prevLogIndex:int, prevLogTerm:int,
                 entries:List[Any], commitIndex: int=0, serial_number:int=None):
        super().__init__(sender, receiver, term, prevLogIndex, prevLogTerm, serial_number=serial_number)
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

class AppendResponseMessage(LogMessage):

    code = "append_response"

    def __init__(self, sender:str, receiver:str, term:int, prevLogIndex:int, prevLogTerm:int,  maxIndex: int,
                 success: bool, leaderId: str, serial_number:int=None):
        super().__init__(sender, receiver, term, prevLogIndex, prevLogTerm, reply_to_type=AppendEntriesMessage, serial_number=serial_number)
        self.leaderId = leaderId
        self.success = success
        self.maxIndex = maxIndex
        
    def __repr__(self):
        msg = super().__repr__()
        msg += f" s={self.success} mi={self.maxIndex} li={self.leaderId}"
        return msg
