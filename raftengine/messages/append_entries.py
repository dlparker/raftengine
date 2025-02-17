from typing import Any, List
from .base_message import BaseMessage
from raftengine.log.log_api import LogRec


class AppendEntriesMessage(BaseMessage):


    def __init__(self, sender:str, receiver:str, term:int, prevLogIndex:int, prevLogTerm:int,
                 entries:List[Any], commitIndex: int=0):
        BaseMessage.__init__(self, sender, receiver, term, prevLogIndex, prevLogTerm)
        self.code = "append_entries"
        self.entries = entries
        self.commitIndex = commitIndex

    @property
    def dialog_id(self):
        return f"{self.term}-{self.prevLogIndex}-{self.prevLogTerm}"

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
    
    @property
    def dialog_id(self):
        return f"{self.term}-{self.prevLogIndex}-{self.prevLogTerm}"

    def replies_to(self, append_msg):
        if self.dialog_id == append_msg.dialog_id:
            return True
        return False
        
    def __repr__(self):
        msg = super().__repr__()
        msg += f" e={len(self.entries)} r={len(self.results)}"
        return msg

