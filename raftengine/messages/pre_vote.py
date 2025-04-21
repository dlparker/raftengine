from .base_message import BaseMessage


class PreVoteMessage(BaseMessage):

    code = "pre_vote"

    def __init__(self, sender:str, receiver:str, term:int, prevLogIndex:int, prevLogTerm:int):
        BaseMessage.__init__(self, sender, receiver, term, prevLogIndex, prevLogTerm)

class PreVoteResponseMessage(BaseMessage):

    code = "pre_vote_response"

    def __init__(self, sender:str, receiver:str, term:int, prevLogIndex:int, prevLogTerm:int, vote:bool):
        BaseMessage.__init__(self, sender, receiver, term, prevLogIndex, prevLogTerm, reply_to_type=PreVoteMessage)
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

