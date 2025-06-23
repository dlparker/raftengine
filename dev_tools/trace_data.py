from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional
import json
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
class TableWrap:
    start_pos: int
    description: str
    is_prep: Optional[bool] = False
    test_path: Optional[str] = None
    test_doc_string: Optional[str] = None
    end_pos: Optional[int] = None
    lines: Optional[list] = None
    condensed: Optional[list] = None
    max_nodes: Optional[int] = None
    features: Optional[list] = field(default_factory=list)

    def count_nodes(self, lines):
        max_nodes = 0
        for line in lines:
            max_nodes = max(max_nodes, len(line))
        self.max_nodes = max_nodes
        return max_nodes
            
class TestTraceData:

    def __init__(self, lines, wraps):
        self.trace_lines = lines
        self.table_wraps = wraps


def write_trace_file(trace_data, filepath):
    rdata = json.dumps(trace_data, default=lambda o:o.__dict__, indent=4)
    with open(filepath, 'w') as f:
        f.write(rdata)

    tmp = read_trace_file(filepath)
        
def read_trace_file(filepath):

    with open(filepath, 'r') as f:
        buff = f.read()

    in_data = json.loads(buff)

    lines = []
    for inline in in_data['trace_lines']:
        outline = []
        for item in inline:
            outline.append(NodeState.from_dict(item))
        lines.append(outline)
    wraps = {}
    for pos,inwrap in in_data['table_wraps'].items():
        wraps[pos] = TableWrap(**inwrap)

    return TestTraceData(lines=lines, wraps=wraps)
            
        
    

    
