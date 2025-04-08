from dataclasses import dataclass
from enum import Enum
from typing import Optional


class MessageCode(str, Enum):

    request_vote =  "REQUEST_VOTE"

    request_vote_response =  "REQUEST_VOTE_RESPONSE"

    append_entries =  "APPEND_ENTRIES"

    append_entries_response =  "APPEND_ENTRIES_RESPONSE"

    def __str__(self):
        return self.value
    
    
class CommsEdge(str, Enum):

    # Pausing here means that the node has
    # completed the processing required in
    # order to send the message, but it
    # has not yet been delivered to the
    # target node. The target node
    # cannot receive the message until
    # this node is resumed. 
    before_send = "BEFORE_SEND"
    
    # Pausing here means that the node has
    # completed the processing required
    # in order to send the message and the
    # handoff has been made to the input
    # processing at the target node. Unless
    # target node is paused or pauses as
    # a result of this message, then it
    # will process the message.
    after_send = "AFTER_SEND"

    # Pausing here means that the simulated
    # network transport is complete and
    # the message is ready to be processed
    # but the node will not "receive" it,
    # e.g. the handler for the message will
    # not run.
    before_handle = "BEFORE_HANDLE"

    # Pausing here means that the simulated
    # network transport is complete and
    # the message has been delivered to the
    # handler. Since everything is async,
    # there is no way to know how much, if
    # any, of the handler code has run at this
    # point, but it will complete before
    # any other pause points are reached.
    after_handle = "AFTER_HANDLE"
    
    # Pausing here is like the after_send
    # case, but this point occurs when
    # the same type of message has been
    # sent to all the other nodes in the cluster,
    # not just one.
    after_broadcast = "AFTER_BROADCAST"

    # Pausing here is like the after_handle
    # case, but this point occurs when
    # the same type of message has been
    # received from all the other nodes in the cluster,
    # not just one.
    after_all_responses = "AFTER_ALL_RESPONSES"

    
    def __str__(self):
        return self.value
    
class ActionCode(str, Enum):

    # The node targeted with this action will
    # pause operations as soon as
    # it completes any message handling that
    # is already in progress. It will not
    # process any other messages or respond to any
    # timeouts until resumed
    pause = "PAUSE"
    
    # The node targeted with this action will
    # do nothing during the phase. 
    noop = "NOOP"
    
    # The node targeted with this action will stay
    # alive, but will be in a new network partition
    # containing a minority of the cluster nodes
    network_to_minority = "NETWORK_TO_MINORITY"

    # The node targeted with this action will
    # rejoin the main cluster network after partition.
    network_to_majority = "NETWORK_TO_MAJORITY"

    # The node targeted with this action will
    # behave as though crashed, will not process
    # any more messages
    crash = "CRASH"

    # The node targeted with this action will
    # behave as though recovered from a crash
    # with log intact
    recover = "RECOVER"

    # The node targeted with this action will
    # behave as though recovered from a crash
    # but an empty log, simulating replacement of a node
    start_as_replacement = "START_AS_REPLACEMENT"
    
    # The node targeted with this action will
    # convert to candidate to start and election
    # but an empty log, simulating replacement of a node
    start_campaign = "START_CAMPAIGN"
    
    # The node targeted with this action will
    # send a heartbeat append entries. Should
    # only be targeted at nodes in the leader state.
    send_heartbeats = "SEND_HEARTBEATS"

    def __str__(self):
        return self.value

class RoleCode(str, Enum):

    leader = "LEADER"
    follower = "FOLLOWER"
    candidate = "CANDIDATE"
    
    def __str__(self):
        return self.value
    
class RunState(str, Enum):

    normal = "NORMAL"
    paused = "PAUSED"
    crashed = "CRASHED"
    
    def __str__(self):
        return self.value

class NetworkMode(str, Enum):
    """ This assumes we only need to care about a single
    partition event, not multiple simultaneous partitions. So
    a node is either part of the majority network, or it
    is part of a single minority network. If analysis
    shows that multiple minority networks are logically
    different in protocol execution terms, then this
    needs revision."""
    majority = "MAJORITY"
    minority = "MINORITY"
    
    def __str__(self):
        return self.value
    
@dataclass
class LogState:
    term: int
    index: int
    last_term: int
    commit_index: int
    leader_id: Optional[str] = None

@dataclass
class NodeState:
    node_id: int
    role: RoleCode
    run_state: RunState
    network_mode: NetworkMode
    log_state: LogState
    uri: Optional[str] = None

    def __post_init__(self):
        if self.uri is None:
            # this is tied to uri generation in the PausingCluster and PausingServer classes
            self.uri = f"mcpy://{self.node_id}"

@dataclass
class CommsOp:
    message_code: MessageCode
    comms_edge: CommsEdge

@dataclass
class ActionOnMessage:
    comms_op: CommsOp
    action_code: ActionCode
    run_till_trigger: bool = True
    description: str = None
    

@dataclass
class ActionOnState:
    log_state: LogState
    action_code: ActionCode
    run_till_trigger: bool = True

@dataclass
class ValidateState:
    log_state: LogState
    good_on_equal: bool = True

@dataclass
class DoNow:
    action_code: ActionCode
    description: str = None

@dataclass
class NoOp:
    action_code: ActionCode = ActionCode.noop 
    description: str = None

class PhaseStep:

    def __init__(self, node_uri, runner_class=None, validate_class=None, do_now_class=None, description=None):
        self.node_uri = node_uri
        self.runner_class = runner_class
        self.validate_class = validate_class
        self.do_now_class = do_now_class
        self.description = description
        self.is_noop = False
        # Validate the action and validate classes 
        if runner_class is None and validate_class is None and do_now_class is None:
            self.is_noop = True
        elif runner_class:
            for key in ['action_code', 'run_till_trigger']:
                if not hasattr(runner_class, key):
                    raise Exception(f'supplied runner class does not have {key} attr')
        elif validate_class:
            for key in ['good_on_equal',]:
                if not hasattr(validate_class, key):
                    raise Exception(f'supplied validate class does not have {key} attr')
        elif do_now_class:
            for key in ['action_code',]:
                if not hasattr(do_now_class, key):
                    raise Exception(f'supplied do_now class does not have {key} attr')
    
    def get_msg_runner(self):
        if self.runner_class:
            if hasattr(self.runner_class, 'comms_op'):
                return self.runner_class
        return None
    
    def get_state_runner(self):
        if self.runner_class:
            if hasattr(self.runner_class, 'log_state'):
                return self.runner_class
        return None

    def get_state_validate(self):
        if self.validate_class:
            return self.validate_class
        return False

    def get_do_now(self):
        if self.do_now_class:
            return self.do_now_class
        return None
    

@dataclass
class Phase:
    node_ops: list[PhaseStep] # must have all nodes even if the action is nothing
    description: str = None

class Sequence:

    def __init__(self, start_state=None, node_count=3, description=None):
        self.start_state = start_state
        self.node_count = node_count
        self.description = description
        self.phases = []
        self.phase_cursor = 0
        self.nodes = {}
        self.nodes_by_id = {}
        if self.start_state:
            if node_count and len(self.start_state.nodes) != node_count:
                raise Exception('node_count and start_state inconsistent, prolly supply one or the other')
            self.node_count = 0
            for node in self.start_state.nodes:
                if node.uri in self.nodes:
                    raise Exception(f'node.uri {node.uri} used twice in supplied start state')
                self.nodes[node.uri] = node
                self.nodes_by_id[node.node_id] = node
                self.node_count += 1
        else:
            node_list = []
            for i in range(1, self.node_count + 1):
                node = NodeState(i, RoleCode.follower, RunState.normal, NetworkMode.majority,
                                 LogState(0, 0, 0, 0, None))
                self.nodes[node.uri] = node
                self.nodes_by_id[node.node_id] = node
                node_list.append(node)
            self.start_state = ClusterState(node_list)

    def add_phase(self, phase):
        found_uris = []
        for node_op in phase.node_ops:
            if node_op.node_uri not in self.nodes:
                raise Exception(f'cannot add node {node_op.node_uri} to phase, not in sequence node dict')
            found_uris.append(node_op.node_uri)
            
        if len(found_uris) !=  len(self.nodes):
            raise Exception(f'phase has {len(found_uris)}, not expected {len(self.nodes)}, must be duplicates')
        self.phases.append(phase)

    def next_phase(self):
        if self.phase_cursor > len(self.phases) - 1:
            return None
        phase = self.phases[self.phase_cursor]
        self.phase_cursor += 1
        return phase

    def clear_phases(self):
        """ allows the cluster to be reused for another sequences, starting whereever this one
        left off by defining new phases"""
        self.phases = []
        self.phase_cursor = 0


@dataclass
class ClusterState:
    nodes: list[NodeState]
    


