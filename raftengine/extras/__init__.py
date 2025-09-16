import abc
class RPCClientAPI(abc.ABC):

    @abc.abstractmethod
    def __init__(self, host, port, timeout=1.0):
        raise NotImplementedError

class RPCServer(abc.ABC):

    @abc.abstractmethod
    def __init__(self, raft_server, rm_wait_for_result=False):
        raise NotImplementedError
