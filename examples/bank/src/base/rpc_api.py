from abc import ABC, abstractmethod
from raftengine.api.deck_api import CommandResult

class RPCAPI(ABC): 
    """Abstract base class defining the RPC interface for banking implementations"""
    
    @abstractmethod
    def get_uri(self) -> str:
        """ return the uri for the target server"""
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
    
    
