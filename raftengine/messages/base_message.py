"""
How to add a new message type:

Extend the BaseMessage class, giving your new class a unique string value 
for the class variable "code". 

"""
from typing import Type

pair_mapping = {}
class BaseMessage:

    code = "invalid"
    
    def __init__(self, sender:str, receiver:str, reply_to_type=None):
        self.sender = sender
        self.receiver = receiver
        self.code = self.__class__.code
        if reply_to_type:
            pair_mapping[self.__class__] = reply_to_type

    def is_reply_to(self, other):
        global pair_mapping
        paired = pair_mapping.get(self.__class__, None)
        if paired and paired == other.__class__:
            if other.sender == self.receiver and other.receiver == self.sender:
                if hasattr(self, 'prevLogTerm') and hasattr(other, 'prevLogTerm'):
                    if(other.term == self.term
                       and other.prevLogTerm == self.prevLogTerm
                       and other.prevLogIndex == self.prevLogIndex):
                        return True
        return False

    @classmethod
    def from_dict(cls, data):
        copy_of = dict(data)
        del copy_of['code']
        msg = cls(**copy_of)
        return msg
    
    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        msg = f"{self.code}:{self.sender}->{self.receiver}: "
        return msg
    
    @classmethod
    def get_code(cls):
        return cls.code

    

