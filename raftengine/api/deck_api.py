import abc
from typing import List, Any, Optional
from enum import Enum
from dataclasses import dataclass
from raftengine.api.log_api import LogAPI, LogRec
from raftengine.api.events import EventHandler
from raftengine.api.pilot_api import PilotAPI
from raftengine.api.deck_config import ClusterInitConfig, LocalConfig
from raftengine.api.snapshot_api import SnapShot, SnapShotToolAPI
from raftengine.api.types import ClusterSettings, ClusterConfig

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

class DeckAPI(abc.ABC):
    """
    Main entry and control point for RaftEngine library.
    
    Caller supplies a PilotAPI implementation and both local and cluster config data to
    configure the raft library, then calls start when ready to join the consensus cluster.

    Note that the cluster config data that is suppled during init is only used if the
    cluster configuration is not stored in the log, which essentially means only on the
    first run of this particular server instance. Any subsequent run will ignore the supplied
    config data in favor of that which is stored in the log.

    The general flow of a server's life time is that some piece of users code starts a process,
    collects some basic configuration such as the communication endpoint address (typically referred
    to in this library as a "URI" or "uri"), and probably the externally defined initial cluster
    configuration, which is mainly a list of URIs for other servers in the cluster.

    Any commnications channel setup is completed, then the server code instantials an implementation
    of the :py:class:`raftengine.api.pilot_api.PilotAPI` instance, providing it with a :py:class:`raftengine.api.log_api.LogAPI`
    instance and whatever other state and services it needs to function, including commnications
    channels, the application "state machine", etc.

    Once all that is complete, the server code calls api.get_deck_class() to get a reference
    to the implementation of this interface class, then creates an instance using the config data and
    the :py:class:`raftengine.api.pilot_api.PilotAPI` api instance.

    This completes the initialization of the raft engine, but it is not yet runnning. To start it,
    the server code should call the start method and then function in a way that supports proper
    async operations so as to let the raft engine run as needed.

    At some point the server will either receive a message from the cluster Leader, or will participate
    in an election with messages both coming in and going out. Incomming message delivery is
    the responsibility of the DeckAPI implementation and outgoing message delivery is the responsibilty
    of the PilotAPI implememtation.

    The implementer supplies the incoming message passing mechansim by calling the on_message method.
    The PilotAPI implementaton accepts outgoing messaages from the  send_message and send_response methods
    of that api. 
    
    Eventually the election will complete and the server will be either a follower or the Leader.
    
    When the server functions dictate that it should be performing a raft mediated command, it should
    call the :py:meth:`run_command` method which will start the raft consensus building
    process, if the server is currently in the leader role, which can be checked by calling
    :py:meth:`is_leader`. When the consenus is achieved, the raft engine will call the
    :py:meth:`raftengine.api.pilot_api.PilotAPI.process_command` method on the supplied PilotAPi implementation.

    Various servers will receive and send various messages and message replies to complete this process.
    
    """

    @abc.abstractmethod
    def __init__(self, cluster_config: ClusterInitConfig, local_config: LocalConfig, pilot: PilotAPI) ->None:
        """
        Initialize the RaftLibrary from the LocalConfig data and possibly the ClusterInitConfig.
        In the case that this is the first time this server instance has joined the cluster,
        the supplied cluster config will be used, otherwise the current config will be retrieved
        from the log. The PilotAPI implementation will be installed in the Deck to be used for
        the services it provides. See :py:class:`raftengine.api.pilot_api.PilotAPI`.

        :param ClusterInitConfig cluster_config: Initial cluster definition to be used only if there is not one in the log.
        :param LocalConfig local_config: Initial configuration for this server
        :param PilotAPI pilot: Instance of Implementation of PilotAPI.

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

        :rtype: None
        """
        raise NotImplementedError
    
    @abc.abstractmethod
    async def get_leader_uri(self) -> str | None:
        """
        Get the communications endpoint id of the cluster leader, if it is known. If the cluster is currently
        running an election of the server has not yet connected to the leader, then it will not be known.
        raise NotImplementedError
        
        :rtype str: Leader URI or None
        """
        
    @abc.abstractmethod
    async def is_leader(self) -> bool:
        """
        Returns True if this server is the cluster leader.
        
        :rtype bool: 
        """
        raise NotImplementedError
        
    @abc.abstractmethod
    async def start_and_join(self, leader_uri:str) -> None:
        """
        This should only be called for a server that has never been part of the cluster, to join
        the cluster. This may take a while if there are a lot of log records to replicate
        to this server.

        :params str leader: The id string for the leader's communication endpoint, or URI.
        :rtype None: 
        """
        raise NotImplementedError
        
    @abc.abstractmethod
    async def add_event_handler(self, handler:EventHandler) -> None:
        """
        Add a handler for one or more of the events that the raft library can generate.
        See :py:class:`raftengine.api.events.EventHandler`.

        :params EventHandler handler: A handler class instance that extends EventHandler base lass
        :rtype None: 
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def remove_event_handler(self, handler:EventHandler) -> None:
        """
        Remove a previously install event handler.
        :params EventHandler handler: The handler *INSTANCE* to be removed.

        :rtype None:
        """
        raise NotImplementedError
    
    @abc.abstractmethod
    async def on_message(self, in_message:bytes) -> None:
        """
        When the server receives a message for the RaftLibrary, it should pass it to this
        method. 

        :params bytes in_message: The incoming message bytes
        :rtype None:
        
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def run_command(self, command:str, timeout:float = 2.0) -> CommandResult:
        """
        Call this method to run a command through the Raft consensus process.
        Once consesus has been achieved on the associated log update, the command will
        be executed locally and by at least cluster_node_count/2 number of other nodes. Execution
        will call the process_command method of the provided :py:class:`raftengine.api.pilot_api.PilotAPI`
        instance. Once this method returns a success code, the Raft guaranteed of durability is assured.

        :params str command: The command to execute at all cluster servers
        :params float timeout: Maximum time to wait for command to be executed
        :rtype CommandResult: :py:class:`raftengine.api.deck_api.CommandResult`: 
        
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def get_cluster_config(self) -> ClusterConfig:
        """
        Returns the current cluster configuration as stored in the log.

        :rtype ClusterConfig: :py:class:`raftengine.api.types.ClusterConfig` 
        
        """
        raise NotImplementedError
    
    @abc.abstractmethod
    async def update_settings(self, settings:ClusterSettings) -> None:
        """
        Do a standard raft replication which changes the ClusterSettings portion
        of the cluster config. Does not wait for completion, just queues the
        changes and returns. If you care about ensuring that the chanages
        are done, monitor the ClusterConfig for a few milliseconds to detect the update.

        :param ClusterConfig settings: the new settings to apply
        :rtype None:
        
        """
        raise NotImplementedError
    
    @abc.abstractmethod
    async def stop(self) -> None:
        """
        Stop processing RaftState. This node will no longer participate in the
        consensus process. If you call this you should be aware of the impact
        that it has on the cluster, obviously.

        :rtype None:
        """
        raise NotImplementedError
    
    @abc.abstractmethod
    async def take_snapshot(self, timeout=2.0) -> SnapShot:
        """
        This method causes the deck to run the snapshot process.

        :rtype None:
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def exit_cluster(self, timeout=10.0, callback=None) -> None:
        raise NotImplementedError

    
    
