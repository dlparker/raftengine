import abc
from typing import List, Any, Optional
from enum import Enum
from dataclasses import dataclass
from raftengine.api.log_api import LogAPI, LogRec
from raftengine.api.events import EventHandler
from raftengine.api.pilot_api import PilotAPI
from raftengine.api.hull_config import ClusterInitConfig, LocalConfig

@dataclass
class CommandResult:
    command: str
    result: Optional[str] = None
    committed: bool = False
    retry: bool = False
    redirect: Optional[str] = None
    logRec: Optional[LogRec] = None
    error: Optional[str] = None
    timeout_expired: Optional[bool] = False

    
class HullAPI(abc.ABC):
    """ Main entry and control point for RaftEngine library. Caller supplies a PilotAPI implementation
    and both local and cluster config data to configure the raft library, then calls start when ready
    to join the consensus cluster. Note that the cluster config data that is suppled during init
    is only used if the cluster configuration is not stored in the log, which essentially means on
    the first run of this particular server instance. Any subsequent run will ignore the supplied
    config data in favor of that which is stored in the log.

    The caller supplies the message passing mechansim via the on_message method, for incomming messages,
    and the send_message and send_response methods of the PilotAPI implementation. The library works properly
    with asynchronous messages, so message passing and RPC mechanism are both fine.
    
    """
    
    @abc.abstractmethod
    def __init__(self, cluster_config: ClusterInitConfig, local_config: LocalConfig, pilot: PilotAPI):
        """
        Initialize the RaftLibrary from the LocalConfig data and possibly the ClusterConfig
        data in the case that this is the first time this server instance has joined the cluster.
        Install the PilotAPI impementation as the other side of the API interface with the
        RaftEngine libary.
        """
        raise NotImplementedError
    
    @abc.abstractmethod
    async def start(self):
        """
        Begin processing RaftState. Note that much of the Raft behavior is timeout based, so
        the caller must ensure that it does not block the library for long. If the caller program
        is written as async then this should be an ordinary requirement for the rest of the code,
        and the timeouts are typically in milliseconds so it is not very hard to avoid blocking
        the library. If the caller's code is not written as async then this code should probably
        be run in a separate thread or process.
        """
        raise NotImplementedError
    
    @abc.abstractmethod
    async def get_leader_uri(self) -> str:
        raise NotImplementedError
        
    @abc.abstractmethod
    async def start_and_join(self, leader_uri:str) -> None:
        """
        This should only be called for a server that has never been part of the cluster, to join
        the cluster. This may take a while if there are a lot of log records to replicate
        to this server. 
        """
        raise NotImplementedError
        
    @abc.abstractmethod
    async def add_event_handler(self, handler:EventHandler) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    async def remove_event_handler(self, handler:EventHandler) -> None:
        raise NotImplementedError
    
    @abc.abstractmethod
    async def on_message(self, in_message:str) -> None:
        """
        When the server receives a message for the RaftLibrary, it should pass it to this
        method. 
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def run_command(self, command:str, timeout:float = 2.0) -> CommandResult:
        """
        Call this method to run a command through the Raft consensus process.
        Once consesus has been achieved on the associated log update, the command will
        be executed locally and by at least cluster_node_count/2 number of other nodes. Execution
        will call the process_command method of the provided PilotAPI instance. Once this
        method returns a success code, the Raft guaranteed of durability is assured.
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def stop(self) -> None:
        """
        Stop processing RaftState. This node will no longer participate in the
        consensus process. If you call this you should be aware of the impact
        that it has on the cluster, obviously.
        """
        raise NotImplementedError
    
    @abc.abstractmethod
    async def exit_cluster(self, timeout=10.0, callback=None) -> None:
        raise NotImplementedError
