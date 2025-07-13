"""
"""
from typing import Type
from raftengine.messages.base_message import BaseMessage

class LogMessage(BaseMessage):

    code = "invalid"
    
    def __init__(self, sender:str, receiver:str, term:int, prevLogIndex:int, prevLogTerm:int, reply_to_type=None, serial_number:int=None):
        super().__init__(sender, receiver, reply_to_type, serial_number)
        self.term = term
        self.prevLogIndex = prevLogIndex
        self.prevLogTerm = prevLogTerm

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        msg = super().__repr__()
        msg += f"t={self.term},pI={self.prevLogIndex},pt={self.prevLogTerm}"
        return msg
    
    

