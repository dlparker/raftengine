from .base_message import BaseMessage


class TransferPowerMessage(BaseMessage):

    code = "transfer_power"

        
class TransferPowerResponseMessage(BaseMessage):

    code = "transfer_power_response"

    def __init__(self, sender:str, receiver:str, term:int, prevLogIndex:int, prevLogTerm:int, success:bool):
        BaseMessage.__init__(self, sender, receiver, term, prevLogIndex, prevLogTerm)
        self.success = success

    @classmethod
    def from_dict(cls, data):
        copy_of = dict(data)
        del copy_of['code']
        msg = cls(**copy_of)
        return msg
        
    def __repr__(self):
        msg = super().__repr__()
        msg += f" ok={self.success}"
        return msg

