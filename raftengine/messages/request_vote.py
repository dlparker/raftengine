from raftengine.messages.log_msg import LogMessage



class RequestVoteMessage(LogMessage):

    code = "request_vote"

class RequestVoteResponseMessage(LogMessage):

    code = "request_vote_response"

    def __init__(self, sender:str, receiver:str, term:int, prevLogIndex:int, prevLogTerm:int, vote:bool, serial_number:int=None):
        super().__init__(sender, receiver, term, prevLogIndex, prevLogTerm, reply_to_type=RequestVoteMessage, serial_number=serial_number)
        self.vote = vote
        
    def __repr__(self):
        msg = super().__repr__()
        msg += f" v={self.vote}"
        return msg

