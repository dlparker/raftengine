from .base_message import BaseMessage


class RequestVoteMessage(BaseMessage):

    code = "request_vote"

class RequestVoteResponseMessage(BaseMessage):

    code = "request_vote_response"

    def __init__(self, sender:str, receiver:str, term:int, prevLogIndex:int, prevLogTerm:int, vote:bool):
        BaseMessage.__init__(self, sender, receiver, term, prevLogIndex, prevLogTerm)
        self.vote = vote

    @classmethod
    def from_dict(cls, data):
        msg = cls(sender=data['sender'],
                  receiver=data['receiver'],
                  term=int(data['term']),
                  prevLogIndex=int(data['prevLogIndex']),
                  prevLogTerm=int(data['prevLogTerm']),
                  vote=bool(data['vote']))
        return msg
        
    def __repr__(self):
        msg = super().__repr__()
        msg += f" v={self.vote}"
        return msg

    def __eq__(self, other):
        if self.__dict__ == other.__dict__:
            return True
        return False
