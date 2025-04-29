from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
    
class RoleName(str, Enum):

    """ Follower role, as defined in raftengine protocol """
    follower = "FOLLOWER"

    """ Candidate role, as defined in raftengine protocol """
    candidate = "CANDIDATE"

    """ Leader role, as defined in raftengine protocol """
    leader = "LEADER"

    def __str__(self):
        return self.value
    
class OpDetail(str, Enum):

    """ newer term received """
    newer_term = "NEWER_TERM"

    """ newer term received """
    older_term = "OLDER_TERM"

    # --- end expect from any role

    """ Follower has not received timely leader contact """
    leader_lost = "LEADER_LOST"

    """ Follower, leader has called us at least once """
    joined_leader = "JOINED_LEADER"                  

    # --- Expect from Candidate roles
    """ Candidate starting election """
    start_election = "START_ELECTION"

    """ enough votes in, election won """
    won = "WON"

    """ enough votes in, election lost """
    lost = "LOST"

    """ enough votes in, election lost """
    election_timeout = "ELECTION_TIMEOUT"

    """ Candidate starting new election """
    start_new_election = "START_NEW_ELECTION"

    """ Candidate starting election pre-vote"""
    start_pre_election = "START_PRE_ELECTION"

    """ enough pre-votes in, election won """
    pre_won = "PRE_WON"

    """ enough pre-votes in, election lost """
    pre_lost = "PRE_LOST"
    
    """ Sending append_entries to cluster """
    broadcasting_term_start = "BROADCASTING_TERM_START"

    """ Sending catchup log records to follower """
    sending_catchup = "SENDING_CATCHUP"

    """ Sending catchup log records to follower using backdown method """
    sending_backdown = "SENDING_BACKDOWN"

    
    def __str__(self):
        return self.value

class CommandSerialRange:
    """ Command serial number generated for client 
    (when requested) will be in this range. This 
    is the range of an unsigned integer of 64 bits.
    Python can handle larger numbers, but this 
    is a convenient restriction that aids other
    languages, should they use this library,
    and that's a pretty high limit!
    """
    min_value = 1
    max_value = 18_446_744_073_709_551_615

@dataclass
class NodeRec:
    uri: str
    is_adding: bool = field(default = False)   # config change to add this is in flight
    is_removing: bool = field(default = False) # config change to remmove this is in flight

@dataclass
class ClusterSettings:
    heartbeat_period: float = field(default = 0.01)
    election_timeout_min: float = field(default = 0.150)
    election_timeout_max: float = field(default = 0.300)
    max_entries_per_message: int = field(default = 20)
    use_pre_vote: bool = field(default = True)
    use_check_quorum: bool = field(default = True)
    use_dynamic_config: bool = field(default = True)
    
@dataclass
class ClusterConfig:
    nodes: dict[str,NodeRec] = field(default_factory=dict)
    pending_node: Optional[NodeRec] = field(default=None)
    settings: ClusterSettings = field(default_factory=lambda: ClusterSettings())
    
