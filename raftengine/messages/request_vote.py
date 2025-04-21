from .base_message import BaseMessage


class RequestVoteMessage(BaseMessage):

    code = "request_vote"

class RequestVoteResponseMessage(BaseMessage):

    code = "request_vote_response"

    def __init__(self, sender:str, receiver:str, term:int, prevLogIndex:int, prevLogTerm:int, vote:bool):
        BaseMessage.__init__(self, sender, receiver, term, prevLogIndex, prevLogTerm, reply_to_type=RequestVoteMessage)
        self.vote = vote

    @classmethod
    def from_dict(cls, data):
        copy_of = dict(data)
        del copy_of['code']
        msg = cls(**copy_of)
        return msg
        
    def __repr__(self):
        msg = super().__repr__()
        msg += f" v={self.vote}"
        return msg

