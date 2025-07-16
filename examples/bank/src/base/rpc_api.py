from abc import ABC, abstractmethod
from raftengine.api.deck_api import CommandResult

class RPCAPI(ABC): 
    """Abstract base class defining the RPC interface for banking implementations"""
    
    @abstractmethod
    def get_uri(self) -> str:
        """ Client side only, no rpc support, return the uri for the target server"""
        raise NotImplemented
    
    @abstractmethod
    async def raft_message(self, message:str) -> None:
        """ Message transport for Raftengine library, sends a message, reply is always None"""
        raise NotImplemented
    
    @abstractmethod
    async def run_command(self, command:str) -> CommandResult:
        """
        Sends the command as serialized by the Collecter to the server where it is
        routed to the Dispatcher and from there to the Teller.
        """
        raise NotImplemented


class Foo(ABC):

    @abstractmethod
    async def side_command(self, command:str) -> str:
        """
        Sends a serialized command as to the server where it is handled outside
        the raft command logic. Probably should not do read access to anything that
        raft writes because it could be stale, definitely should not write any such
        thing. Useful for adminstration commands for the server process such as
        stop, take snapshot, exit cluster, update cluster settings, etc. Cluster
        changes, snapshots, etc. cause Raft writes, but they do it through the
        Deck API and therefore are managed by Raft logic.

        In this example the commands are encoded and decoded with Collector
        and Dispatcher style operations. You may choose a diffferent method
        for your application. You might even choose to give each command
        a first class RPC method. Since these operations have no relevance
        to internal raft operations it is entirely up to you.
        """
        raise NotImplemented
    
    
