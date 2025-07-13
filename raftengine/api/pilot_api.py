import abc
from typing import List, Any
from raftengine.api.log_api import LogAPI
from raftengine.api.snapshot_api import SnapShot, SnapShotToolAPI

class PilotAPI(abc.ABC):
    """
    Service provider interface definition for user supplied Raft support operations.

    The Raft Engine requires some services that support operations, mostly triggered
    by message operations:

    1. Sending messages to other raft engine enabled servers
    2. Sending replies to other raft engine enabled servers
    3. Applying application commands that have been validated by consensus
    4. Managing snapshots
    5. Aquiring the :py:class:`raftengine.api.log_api.LogAPI` instance.  

    Many of these operations are "the other side" of operations performed by
    calling methods on the :py:class:`raftengine.api.deck_api.DeckAPI` instance. For example,
    calling :py:meth:`raftengine.api.deck_api.DeckAPI.run_command` will, after raft consensus
    commit cause the raft engine to call process_command in this class.

    The :py:class:`raftengine.api.log_api.LogAPI` instance will be used by the Raft engine
    to store log records, cluster configuration, snapshot information as defined
    in that API.

    The caller can base their implementation on any foundation they
    want, including a non-persistent model if their application's state is also
    non-persistent. It would be a rare case for both to be ephemeral, but that
    might make sense if the resources managed by the cluster were ephemeral too.
    Maybe a live chat server where clients did not expect any persistent services?

    The more plausible case involves a persistent log. In that case the implementer
    might want to use the log persistence mechanism (a database for example) for
    other application needs as well. Or not.

    """
    @abc.abstractmethod
    def get_log(self) -> LogAPI: 
        """ Provides an implementation of the LogAPI. Can be one of the provided 
        implementations, or something that the library user provides. Providing
        your own gives the opportunity to provide transactional constraints to 
        your own data operations and include the raft log records in those 
        transactions. 
        """
        raise NotImplementedError
    
    @abc.abstractmethod
    async def process_command(self, command: str, serial: int) -> list[str, str]: 
        """
        Called by raft :py:class:`raftengine.api.deck_api.DeckAPI` to trigger
        user defined commands once the raft algorithm has determined
        that the command is safe to apply. This is explained in the
        raft paper.

        The basic theory is that the commands  are submitted to the raft library
        which ensures that there is a consensus among the servers in the cluster
        that the command will be executed. The paper describes the command as
        triggering a transition in the application's state machine.

        The command should be provided to the raft library in the form
        of a string along with an optional application defined serial
        number uniquely identifying this command request. When the
        library determines that the command has achieved raft
        consensus, it will call t his method with the string and the
        serial number.
        
        The implementation of this class is responsible for turning that into
        application activity. Note that the string must make sense to all the servers
        in the cluster, and therefore cannot encode references ephemeral local state,
        unless everything needed to recreate the pre-command state is fully encoded.
        The receiving server my have rebooted at anytime between two commands, so
        the application developer needs to consider the tradeoffs between ephemeral
        and persistent state machines.

        Args:
            command (str): Passed through from the raft library log replication,
                            from some call to :py:meth:`raftengine.api.deck_api.DeckAPI.run_command`
            serial (int): Passed through from the raft library log replication from some c
                           all to :py:meth:`raftengine.api.deck_api.DeckAPI.run_command`
        
        Returns:
            str: Meaning defined by Pilot developer, to be passed back as result from call to :py:meth:`raftengine.api.deck_api.DeckAPI.run_command`

        """
        raise NotImplementedError

    @abc.abstractmethod
    async def send_message(self, target_uri: str, message:bytes) -> None: 
        """
        Called by raft :py:class:`raftengine.api.deck_api.DeckAPI` to when the raft engine
        needs to send a message to another server in the cluster. Pilot implementation
        should send it as soon as possible and not wait for a response.

        Args:
            target_uri (str): The communications endpoint of the target server encoded
                               in a string. Any scheme for doing that is acceptable. URIs
                               are simple and clear, so something like:

                               my_rpc://192.168.100.1:8080
        
                               or
        
                               https://node2:8080

                               etc is good. Any string you know how to interpret is valid.
            message (bytes): The raft message encoded as bytes. 

        Returns:
            None:
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def send_response(self, target_uri: str, orig_message:bytes, reply:bytes) -> None: 
        """
        Called by raft :py:class:`raftengine.api.deck_api.DeckAPI` to when the raft engine
        needs to send a response message to a previously received message. The
        Pilot implementation should send it as soon as possible and not wait for a response.

        Args:
            target_uri (str): The communications endpoint of the target server encoded
                               in a string. Any scheme for doing that is acceptable. URIs
                               are simple and clear, so something like:

                               my_rpc://192.168.100.1:8080
        
                               or
        
                               https://node2:8080

                               etc is good. Any string you know how to interpret is valid.
            orig_message (bytes): The original message to which this is a response
            reply (bytes): The response message encoded as bytes

        Returns:
            None:
        
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def begin_snapshot_import(self, snapshot:SnapShot) -> SnapShotToolAPI:
        """Called by raft :py:class:`raftengine.api.deck_api.DeckAPI` when the raft leader
        has sent a message indicating that the target node should load a snapshot with
        the given log position and term. The Pilot implementation needs to know how
        to work with the application state machine to prepare for this load process.

        The provided SnapShot instance indicates that last Raft log index record prior
        that was applied to the state machine before the snapshot was created. There
        is no expecation that this information will be relevant to how the snapshot is
        stored by the application state machine and is provided just for clarity.

        The application state machine needs to instantiate an implememtation
        of :py:class:`raftengine.api.snapshot_api.SnapShotToolAPI` that can save the
        snapshot data according to whatever scheme the application uses. 

        See :ref:`snapshot_process` for details

        Args:
            index (int): The index of the last log entry that is to be replaced by the snapshot
            term (int): The term of the last log entry that is to be replaced by the snapshot

        
        :rtype: SnapShot

        """
        raise NotImplementedError

    @abc.abstractmethod
    async def begin_snapshot_export(self, snapshot:SnapShot) -> SnapShotToolAPI:
        """

        Called by raft :py:class:`raftengine.api.deck_api.DeckAPI` as raft leader when
        a follower node needs to recieve and install a snapshot. The shapshot
        properties have been retrived from the log and is supplied in case the PilotAPI
        implemetation cares about them, although that is not likely. The
        application state machine snapshot storage mechanism needs to be exposed to the
        leader as and instance of an implememtation of
        :py:class:`raftengine.api.snapshot_api.SnapShotToolAPI`, which will allow the
        leader to collection chunks of the stored snapshot data and send them to the
        follower, where the follower will store them using its own instance of the
        same tool implementation.

        See :ref:`snapshot_process` for the big picture
        
        :param SnapShot snapshot: denotes that index of the last record applied prior to snapshot
                                  creation and the term of that record.
        :rtype: SnapShot: In instance of a :py:class:`raftengine.api.snapshot_api.SnapShotToolAPI`
                          implementation that can deliver the snapshot data in chunks.
        """
        raise NotImplementedError
    
    @abc.abstractmethod
    async def create_snapshot(self, index:int , term: int) -> SnapShot:
        """

        Called by raft :py:class:`raftengine.api.deck_api.DeckAPI` when
        it is commanded to take a snapshot. The application state machine
        that implements the PilotAPI must generate the data for the snapshot
        and return a new :py:class:`raftengine.api.snapshot_api.SnapShot`
        instance. The index will be the last committed log record index
        and the term will be the term saved in that record. This marks
        the last record to be included in the snapshot and makes
        log equivalence checks available in a log that contains only
        the snapshot and is otherwise empty.

        Two options are available for storing the snapshot data. These
        options are selected by either providing a
        :py:class:`raftengine.api.snapshot_api.SnapShotToolAPI` instance
        or not in the returned SnapShot. Either way the next step is
        to call the log api "install_snapshot" method. The log will
        behave differently depending on the "tool" property of the
        SnapShot. 

        If a tool is not supplied in the SnapShot, then the application
        must provide persistence for the data directly,
        ensuring that it can be retrieved in future when provided
        with a matching SnapShot instance at a later time.

        If the application wants the data to be stored by the
        :py:class:`raftengine.api.log_api.LogAPI` implementaion,
        then it should create a an implementation of
        the :py:class:`raftengine.api.snapshot_api.SnapShotToolAPI` API
        that has access to whatever temporary storge contains the
        snapshot data (more on that below) and place a reference
        to an instance of that class in the "tool" property
        of the SnapShot. The log instance will then collected the
        data via the calls to the "get_snapshot_chunk" method of the tool
        and it will persist the chunks for later retreval.

        """
        
    @abc.abstractmethod
    async def stop_commanded(self) -> None:
        """ This server has been commanded to stop raft operations, probably
        because it has been removed from the cluster. The Pilot implememntation
        should shutdown operations that rely on raft mechanisms.

        :rtype: None
        """
        raise NotImplementedError

