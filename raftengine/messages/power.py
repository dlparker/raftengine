from raftengine.messages.log_msg import LogMessage


class TransferPowerMessage(LogMessage):

    code = "transfer_power"

        
class TransferPowerResponseMessage(LogMessage):

    code = "transfer_power_response"

    def __init__(self, sender:str, receiver:str, term:int, prevLogIndex:int, prevLogTerm:int, success:bool, serial_number:int=None):
        super().__init__(sender, receiver, term, prevLogIndex, prevLogTerm, reply_to_type=TransferPowerMessage, serial_number=serial_number)
        self.success = success

        
    def __repr__(self):
        msg = super().__repr__()
        msg += f" ok={self.success}"
        return msg

