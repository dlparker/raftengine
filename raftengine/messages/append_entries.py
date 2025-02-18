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

    # Convenience method for programmers, normal operationss
    # encode by calling to_json
    def encode_entries(self):
        if len(self.entries) == 0:
            self.entries = "[]"
        if not isinstance(self.entries[0], LogRec):
            return
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
        self.entries = result

    def to_json(self):
        # in case no one has decoded the entries yet
        self.deccode_entries()
        self.entries = json.dumps(self.entries, default=lambda o:o.__dict__)
        
    @classmethod
    def from_dict(cls, data):
        entries = []
        for dic in data['entries']:
            entries.append(LogRec.from_dict(dic))
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
        msg += f" e={len(self.entries)}"
        return msg

class AppendResponseMessage(BaseMessage):

    code = "append_response"

    def __init__(self, sender:str, receiver:str, term:int, prevLogIndex:int, prevLogTerm:int,
                 entries:List[Any], results:List[Any],
                 myPrevLogIndex:int, myPrevLogTerm:int, leaderId: str):
        BaseMessage.__init__(self, sender, receiver, term, prevLogIndex, prevLogTerm)
        self.myPrevLogIndex = myPrevLogIndex 
        self.myPrevLogTerm = myPrevLogTerm
        self.entries = entries
        self.results = results
        self.leaderId = leaderId

    def replies_to(self, append_msg):
        if self.dialog_id == append_msg.dialog_id:
            return True
        return False
        
    def __repr__(self):
        msg = super().__repr__()
        msg += f" e={len(self.entries)} r={len(self.results)}"
        return msg

