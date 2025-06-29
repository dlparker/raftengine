from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional
import json
from raftengine.messages.request_vote import RequestVoteMessage,RequestVoteResponseMessage
from raftengine.messages.pre_vote import PreVoteMessage,PreVoteResponseMessage
from raftengine.messages.append_entries import AppendEntriesMessage, AppendResponseMessage
from raftengine.messages.power import TransferPowerMessage, TransferPowerResponseMessage
from raftengine.messages.cluster_change import MembershipChangeMessage, MembershipChangeResponseMessage, ChangeOp
from raftengine.messages.snapshot import SnapShotMessage, SnapShotResponseMessage
from raftengine.api.log_api import LogRec

class SaveEvent(str, Enum):
    message_op = "MESSAGE_OP"
    role_changed = "ROLE_CHANGED"
    crashed = "CRASHED"
    recovered = "RECOVERED"
    started = "STARTED"
    net_partition = "NET_PARTITION"
    partition_healed = "PARTITION_HEALED"
    command_started = "COMMAND_STARTED"
    command_finished = "COMMAND_FINISHED"

    def __str__(self):
        return self.value

        
@dataclass
class NodeState:
    save_event: SaveEvent
    uri: str
    log_rec: LogRec
    commit_index: int
    term: int
    role_name: str
    on_quorum_net: bool = True
    is_paused: bool = False
    is_crashed: bool = False
    leader_id: Optional[str] = None
    voted_for: Optional[str] = None
    message_action: Optional[str] = None
    message: Optional[str] = None
    elapsed_time: Optional[float] = None  # only valid for message handled

    @classmethod
    def from_dict(cls, data):
        copy_of = dict(data)
        if data['log_rec']:
            del copy_of['log_rec']
            copy_of['log_rec'] = LogRec.from_dict(data['log_rec'])
        return cls(**copy_of)
        
@dataclass
class TestSection:
    start_pos: int
    description: str
    is_prep: Optional[bool] = False
    test_path: Optional[str] = None
    test_doc_string: Optional[str] = None
    end_pos: Optional[int] = None
    lines: Optional[list] = None
    condensed: Optional[list] = None
    max_nodes: Optional[int] = None
    features: Optional[dict] = None

    def __post_init__(self):
        if self.features:
            for key in ('used', 'tested'):
                if len(self.features[key]) > 0:
                    i1 = self.features[key][0]
                    if not isinstance(i1, str):
                        newl = []
                        for item in self.features[key]:
                            newl.append(str(item))
                        self.features[key] = newl
    
    def count_nodes(self, lines):
        max_nodes = 0
        for line in lines:
            max_nodes = max(max_nodes, len(line))
        self.max_nodes = max_nodes
        return max_nodes
            
class TestTraceData:

    def __init__(self, test_name, test_path, test_doc_string, lines, sections):
        self.test_name = test_name
        self.test_path = test_path
        self.test_doc_string = test_doc_string
        self.trace_lines = lines
        self.test_sections = sections

    def last_section(self):
        if len(self.test_sections) < 1:
            return None
        keys = list(self.test_sections.keys())
        keys.sort()
        return self.test_sections[keys[-1]]

def decode_message(mdict):
    # we don't always need these reconstitued from save json,
    # so we make it easy for code that needs them to do it.
    mtypes = [AppendEntriesMessage,AppendResponseMessage,
              RequestVoteMessage,RequestVoteResponseMessage,
              PreVoteMessage,PreVoteResponseMessage,
              TransferPowerMessage,TransferPowerResponseMessage,
              MembershipChangeMessage,MembershipChangeResponseMessage,
              SnapShotMessage,SnapShotResponseMessage,]
    message = None
    for mtype in mtypes:
        if mdict['code'] == mtype.get_code():
            message = mtype.from_dict(mdict)
    if message is None:
        raise Exception('Message is not decodeable as a raft type')
    return message


            
        
    

    
