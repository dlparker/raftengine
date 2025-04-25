from enum import Enum


class ChangeOp(str, Enum):

    add = "ADD"
    remove = "REMOVE"
    assume_control = "ASSUME_CONTROL" 

    def __str__(self):
        return self.value
    
class MembershipChangeMessage:
    """
    This is a message that a server or client can send to the leader to ask to change
    the status of the target server's membership. It is not used to replicate the change, that is
    done with normal log entry replication.

    In practical terms, only a server that is tying to add itself to the cluster would
    send this message with the "add" op, it probably wouldn't be done by a client, even an
    admin client. It makes no sense for a server to be running but neither already part of
    this cluster nor making this call, as it would be unable to do any raft operations.
    
    Remove makes sense either way, either something external tells the server to exit the
    cluster, or a client tells the leader to tell the target server. Either way a message
    of this type ends up at the leader to get things rolling.
    """

    code = "membership_change"

    def __init__(self, sender:str, receiver:str, op: ChangeOp, target_uri: str):
        self.sender = sender
        self.receiver = receiver
        self.op = op
        self.target_uri = target_uri
        self.code = self.__class__.code

    
    def __repr__(self):
        msg = super().__repr__()
        msg += f" op={self.op} uri={self.target_uri}"
        return msg

    @classmethod
    def get_code(cls):
        return cls.code

    @classmethod
    def from_dict(cls, data):
        copy_of = dict(data)
        del copy_of['code']
        msg = cls(**copy_of)
        return msg


class MembershipChangeResponseMessage:

    code = "membership_change_response"

    def __init__(self, sender:str, receiver:str, op: ChangeOp, target_uri: str, ok: bool):
        self.sender = sender
        self.receiver = receiver
        self.op = op
        self.target_uri = target_uri
        self.ok = ok
        self.code = self.__class__.code

    def is_reply_to(self, other):
        if (other.__class__ == MembershipChangeMessage
            and other.op == self.op
            and other.target_uri == self.target_uri):
            return True
        return False
        
    def __repr__(self):
        msg = super().__repr__()
        msg += f" op={self.op} uri={self.target_uri} ok={self.ok}"
        return msg

    @classmethod
    def get_code(cls):
        return cls.code

    @classmethod
    def from_dict(cls, data):
        copy_of = dict(data)
        del copy_of['code']
        msg = cls(**copy_of)
        return msg
