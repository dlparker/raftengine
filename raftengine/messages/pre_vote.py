from raftengine.messages.log_msg import LogMessage


class PreVoteMessage(LogMessage):

    code = "pre_vote"

    def __init__(self, sender:str, receiver:str, term:int, prevLogIndex:int, prevLogTerm:int, authorized:bool = False, serial_number:int=None):
        super().__init__(sender, receiver, term, prevLogIndex, prevLogTerm, serial_number=serial_number)
        self.authorized = authorized

    def __repr__(self):
        msg = super().__repr__()
        msg += f" auth={self.authorized}"
        return msg

class PreVoteResponseMessage(LogMessage):

    code = "pre_vote_response"

    def __init__(self, sender:str, receiver:str, term:int, prevLogIndex:int, prevLogTerm:int, vote:bool, serial_number:int=None):
        super().__init__(sender, receiver, term, prevLogIndex, prevLogTerm, reply_to_type=PreVoteMessage, serial_number=serial_number)
        self.vote = vote

    def __repr__(self):
        msg = super().__repr__()
        msg += f" v={self.vote}"
        return msg

