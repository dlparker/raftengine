from typing import Any, List
from .base_message import BaseMessage


class AppendEntriesMessage(BaseMessage):

    code = "append_entries"

    def __init__(self, sender:str, receiver:str, term:int, prevLogIndex:int, prevLogTerm:int,
                 entries:List[Any], commitIndex: int=0):
        BaseMessage.__init__(self, sender, receiver, term, prevLogIndex, prevLogTerm)
        self.entries = entries
        self.commitIndex = commitIndex

    @property
    def dialog_id(self):
        return f"{self.term}-{self.prevLogIndex}-{self.prevLogTerm}"
        
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

