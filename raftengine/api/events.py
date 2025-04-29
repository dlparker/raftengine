from enum import Enum
from typing import Optional
import json
from raftengine.messages.base_message import BaseMessage
from raftengine.messages.cluster_change import ChangeOp


class EventType(str, Enum):
    error = "ERROR"
    role_change = "ROLE_CHANGE"
    term_change = "TERM_CHANGE"
    leader_change = "LEADER_CHANGE"
    membership_change_complete = "MEMBERSHIP_CHANGE_COMPLETE"
    membership_change_aborted = "MEMBERSHIP_CHANGE_ABORTED"
    election_op = "ELECTION_OP"
    resync_op = "RESYNC_OP"

    def __str__(self):
        return self.value

class Event:

    event_type = None
    
    def to_json(self):
        return json.dumps(self, default=lambda o:o.__dict__)

class ErrorEvent(Event):

    event_type = EventType.error

    def __init__(self, error):
        self.error = error

class RoleChangeEvent(Event):

    event_type = EventType.role_change

    def __init__(self, new_role:str):
        self.new_role = new_role

class TermChangeEvent(Event):

    event_type = EventType.term_change

    def __init__(self, new_term:int):
        self.new_term = new_term

class LeaderChangeEvent(Event):

    event_type = EventType.leader_change

    def __init__(self, new_leader:str):
        self.new_leader = new_leader

class  MembershipChangeDoneEvent(Event):

    event_type = EventType.membership_change_complete
    
    def __init__(self, op: ChangeOp, new_node_uri):
        self.op = op
        self.new_node_uri = new_node_uri

class MembershipChangeAbortedEvent(Event):

    event_type = EventType.membership_change_aborted
    
    def __init__(self, op: ChangeOp, failed_node_uri):
        self.op = op
        self.failed_node_uri = failed_node_uri

class ElectionEvent(Event):

    event_type = EventType.election_op
    
    def __init__(self, tag):
        self.op = tag

class ResyncEvent(Event):

    event_type = EventType.resync_op
    
    def __init__(self, tag):
        self.op = tag

        
class EventHandler:

    def __init__(self, event_types: list[EventType]):
        self.event_types = event_types

    def events_handled(self) -> list[EventType]:
        return self.event_types
    
    # override this
    async def on_event(self, event: Event) -> None: # pragma: no cover
        raise NotImplementedError('you must supply on_event method')

