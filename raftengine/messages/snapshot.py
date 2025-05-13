"""
"""
from raftengine.messages.log_msg import LogMessage

class SnapShotMessage(LogMessage):

    code = "snapshot"
    
    def __init__(self, sender:str, receiver:str, term:int, prevLogIndex:int, prevLogTerm:int, leaderId:str,
                 offset:int, done:bool, data: bytes, clusterConfig:str = None):
        super().__init__(sender, receiver, term, prevLogIndex, prevLogTerm)
        self.leaderId = leaderId
        self.offset = offset
        self.done = done
        self.data = data
        self.clusterConfig = clusterConfig
        
    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        msg = super().__repr__()
        msg += f"t={self.term},pI={self.prevLogIndex},pt={self.prevLogTerm},o={self.offset},d={self.done}"
        return msg
    
class SnapShotResponseMessage(LogMessage):

    code = "snapshot_response"
    
    def __init__(self, sender:str, receiver:str, prevLogIndex:int, prevLogTerm:int, term:int, offset:int, success=True):
        super().__init__(sender, receiver, term, prevLogIndex, prevLogTerm, reply_to_type=SnapShotMessage)
        self.offset = offset
        self.success = success

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        msg = super().__repr__()
        msg += f"o={self.offset},s={self.success}"
        return msg
    
    

