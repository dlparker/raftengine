import os
import inspect
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from raftengine.api.log_api import LogRec
from dev_tools.features import TestFeatures

warn_no_docstring = True

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


@dataclass
class TestRec:
    test_name: str
    test_path: str 
    description: str
    test_doc_string: str
    start_pos: int
    end_pos: Optional[int] = field(default=None)
    used_raft: list[str] = field(default_factory=list)
    focused_raft: list[str] = field(default_factory=list)
    wraps: dict[int, 'TableWrap'] = field(default_factory=dict)
    condensed_tables: list = field(default=None)
    
    def last_wrap(self):
        if len(self.wraps) < 1:
            return None
        keys = list(self.wraps.keys())
        keys.sort()
        return self.wraps[keys[-1]]
    
@dataclass
class TableWrap:
    start_pos: int
    description: str
    test_path: Optional[str] = None
    test_doc_string: Optional[str] = None
    end_pos: Optional[int] = None
    lines: Optional[list] = None
    condensed: Optional[list] = None
    max_nodes: Optional[int] = None

    def count_nodes(self, lines):
        max_nodes = 0
        for line in lines:
            max_nodes = max(max_nodes, len(line))
        self.max_nodes = max_nodes
        return max_nodes
            

def get_current_test():
    full_name = os.environ.get('PYTEST_CURRENT_TEST').split(' ')[0]
    test_file = full_name.split("::")[0].split('/')[-1].split('.py')[0]
    test_name = full_name.split("::")[1]

    return full_name, test_file, test_name

import inspect

def get_function_from_frame(frame):
    """
    Retrieves the function object associated with a given frame.

    Args:
        frame: The frame object.

    Returns:
        The function object associated with the frame, or None if not found.
    """
    code = frame.f_code
    for name in frame.f_globals:
        obj = frame.f_globals[name]
        if inspect.isfunction(obj) and obj.__code__ is code:
            return obj
    return None

class TestTrace:

    def __init__(self, cluster):
        self.cluster = cluster
        self.node_states = {}
        self.trace_lines = []
        self.table_wraps = {}
        self.test_rec = None
        self.current_wrap = None

    async def start(self):
        tl = []
        for uri,node in self.cluster.nodes.items():
            ns = self.node_states[uri] = await self.create_node_state(node)
            tl.append(deepcopy(ns))
            ns.save_event = None
        self.trace_lines.append(tl)

    async def add_node(self, node):
        ns = self.node_states[node.uri] = await self.create_node_state(node)

    async def create_node_state(self, node):
        ns = NodeState(save_event=SaveEvent.started,
                       uri=node.uri,
                       log_rec=await node.log.read(),
                       term=await node.log.get_term(),
                       commit_index=await node.log.get_commit_index(),
                       role_name=node.get_role_name(),
                       on_quorum_net=node.is_on_quorum_net(),
                       is_paused=node.am_paused,
                       is_crashed=node.am_crashed,
                       leader_id=node.get_leader_id(),
                       voted_for=await node.log.get_voted_for())
        return ns

    async def update_node_state(self, node, ns):
        ns.log_rec = await node.log.read()
        ns.term = await node.log.get_term()
        ns.on_quorum_net = node.is_on_quorum_net()
        ns.commit_index = await node.log.get_commit_index()
        ns.role_name = node.get_role_name()
        ns.is_paused = node.am_paused
        ns.is_crashed = node.am_crashed
        ns.leader_id = node.get_leader_id()
        ns.voted_for  = await node.log.get_voted_for()
        return ns

    def define_test(self, description, used_raft, focused_raft):
        if len(self.trace_lines) > 0:
            raise Exception('must call define_test before starting traced activitities')
        full_name, test_file, test_name = get_current_test()
        frame = inspect.currentframe().f_back
        func = get_function_from_frame(frame)
        doc_string = func.__doc__
        start_pos = 0
        self.test_rec = TestRec(test_name=test_name, test_path=test_file, description=description,
                                   test_doc_string=doc_string, used_raft=used_raft, focused_raft=focused_raft,
                                   start_pos=start_pos)
        nw = TableWrap(description=description, start_pos=start_pos)
        self.test_rec.wraps[start_pos] = nw

    def start_subtest(self, description):
        cw = self.test_rec.last_wrap()
        if cw and cw.end_pos is None:
            cw.end_pos=len(self.trace_lines)-1
        start_pos = len(self.trace_lines)
        nw = TableWrap(start_pos=start_pos, description=description)
        self.test_rec.wraps[start_pos] = nw

    def end_subtest(self):
        breakpoint()
        cw = self.test_rec.last_wrap()
        cw.end_pos = len(self.trace_lines)
        self.test_rec.end_pos = cs.end_pos
        
    def old_start_subtest(self, description, test_path_str=None, test_doc_string=None):
        if warn_no_docstring and test_path_str:
            if test_doc_string is None or test_doc_string.strip() == "":
                print(f'\n\n{"-"*100}\n\n')
                print(f'Test {test_path_str} has no docstring')
                print(f'\n\n{"-"*100}\n\n')
        old_st = self.current_wrap
        if old_st and old_st.end_pos is None:
            old_st.end_pos=len(self.trace_lines)-1,
        st = TableWrap(start_pos=len(self.trace_lines),
                          description=description,
                          test_path=test_path_str,
                          test_doc_string=test_doc_string)
        self.current_wrap = st
        self.table_wraps[st.start_pos] = st

    def old_end_subtest(self):
        cw = self.current_wrap
        cw.end_pos = len(self.trace_lines)
        self.current_wrap = None

    async def save_trace_line(self):
        # We write a new trace line for any change to any node, and each
        # trace line records everything about every node.
        # This is not efficient, but it cannot result in confusion about
        # order
        tl = []
        for uri,node in self.cluster.nodes.items():
            # nodes can get added after startup
            if uri not in self.node_states:
                ns = self.node_states[uri] = await self.create_node_state(node)
                tl.append(deepcopy(ns))
                ns.save_event = None
                tl.append(deepcopy(ns))
            ns = self.node_states[uri]
            ns = await self.update_node_state(node, ns)
            tl.append(deepcopy(ns))
        self.trace_lines.append(tl)

    async def note_role_changed(self, node):
        ns = self.node_states[node.uri]
        ns.save_event = SaveEvent.role_changed
        await self.save_trace_line()
        ns.save_event = None

    async def note_command_started(self, node):
        ns = self.node_states[node.uri]
        ns.save_event = SaveEvent.command_started
        await self.save_trace_line()
        ns.save_event = None

    async def note_command_finished(self, node):
        ns = self.node_states[node.uri]
        ns.save_event = SaveEvent.command_finished
        await self.save_trace_line()
        ns.save_event = None

    async def note_partition(self, node):
        min_net = self.cluster.net_mgr.get_minority_networks()[0]
        ns = self.node_states[node.uri]
        ns.save_event = SaveEvent.net_partition
        await self.save_trace_line()
        ns.save_event = None

    async def note_heal(self, node):
        # just pick one
        ns = self.node_states[node.uri]
        ns.save_event = SaveEvent.partition_healed
        await self.save_trace_line()
        ns.save_event = None

    async def note_crash(self, node):
        ns = self.node_states[node.uri]
        ns.save_event = SaveEvent.crashed
        await self.save_trace_line()
        ns.save_event = None

    async def note_recover(self, node):
        ns = self.node_states[node.uri]
        ns.save_event = SaveEvent.recovered
        await self.save_trace_line()
        ns.save_event = None

    async def note_blocked_message(self, target, message):
        ns = self.node_states[target.uri]
        ns.save_event = SaveEvent.message_op
        ns.message = message
        ns.message_action = "blocked_in"
        await self.save_trace_line()
        ns.save_event = None
        ns.message = None
        ns.message_action = None

    async def note_queued_in_message(self, target, message):
        ns = self.node_states[target.uri]
        ns.save_event = SaveEvent.message_op
        ns.message = message
        ns.message_action = "queued_in"
        await self.save_trace_line()
        ns.save_event = None
        ns.message = None
        ns.message_action = None

    async def note_message_handled(self, target, message, elapsed_time):
        ns = self.node_states[target.uri]
        ns.save_event = SaveEvent.message_op
        ns.message = message
        ns.message_action = "handled_in"
        await self.save_trace_line()
        ns.save_event = None
        ns.message = None
        ns.message_action = None
        ns.elapsed_time = elapsed_time

    async def note_blocked_send(self, sender, message):
        ns = self.node_states[sender.uri]
        ns.save_event = SaveEvent.message_op
        ns.message = message
        ns.message_action = "blocked_send"
        await self.save_trace_line()
        ns.save_event = None
        ns.message = None
        ns.message_action = None

    async def note_lost_send(self, sender, message):
        ns = self.node_states[sender.uri]
        ns.save_event = SaveEvent.message_op
        ns.message = message
        ns.message_action = "lost_send"
        await self.save_trace_line()
        ns.save_event = None
        ns.message = None
        ns.message_action = None

    async def note_message_sent(self, sender, message):
        ns = self.node_states[sender.uri]
        ns.save_event = SaveEvent.message_op
        ns.message = message
        ns.message_action = "sent"
        await self.save_trace_line()
        ns.save_event = None
        ns.message = None
        ns.message_action = None

    def to_condensed_org(self, include_legend=True):
        if len(self.trace_lines) == 0:
            return []
        tables = self.to_condensed_tables()
        all_rows = []
        for t_index, table in enumerate(tables):
            if table.test_path:
                try:
                    full_name, tfile, test_name = get_current_test()
                except Exception:
                    test_name = ""
                all_rows.append(f"* Test {test_name} from file {table.test_path}")
                all_rows.append("")
            if table.test_doc_string:
                all_rows.append(table.test_doc_string)
                all_rows.append("")
            if len(all_rows) > 1:
                break
        if include_legend:
            all_rows.append("")
            all_rows.append(" *[[condensed Trace Table Legend][Table legend]] located after last table in file*")
            all_rows.append("")
        for t_index, table in enumerate(tables):
            max_chars = 0
            # get the column widths
            row0 = table.condensed[0]
            col_widths = [0 for col in row0 ]
            trows = []
            for row in table.condensed:
                for col_index, col in enumerate(row):
                    col_widths[col_index] = max(col_widths[col_index], len(str(col)))
            trows.append(f"** {table.description}")
            for row in table.condensed:
                str_line = "| "
                for col_index, col in enumerate(row):
                    str_line += f"{col:{col_widths[col_index]}s} |"
                trows.append(str_line)
                max_chars = max(max_chars, len(str_line))
            #trows.append(f" End of {table.description}")
            trows.append('-' * max_chars)
            final_rows = [trows[0],]
            final_rows.append('-' * max_chars)
            final_rows.extend(trows[1:])
            all_rows.extend(final_rows)
            if False:
                for trow in final_rows:
                    print(trow)
        if include_legend:
            legend_path = Path(Path(__file__).parent, "table_legend.org")
            with open(legend_path, 'r') as f:
                buff = f.read()
            for lline in buff.split('\n'):
                all_rows.append(lline)
        return all_rows

    def to_csv(self):
        cols = []
        cols.append('event')
        cols.append('event_node')
        cols.append('message_sender')
        cols.append('message_target')
        cols.append('message_status')
        cols.append('message_type')
        cols.append('entries_count')
        cols.append('commit_index')
        cols.append('reply_entries_ok')
        cols.append('reply_max_index')
        cols.append('elapsed_time')
        # we need to know the max nodes at any point during the test, as it can change
        max_nodes = 0
        for line in self.trace_lines:
            max_nodes = max(max_nodes, len(line))
        for i in range(1, max_nodes + 1):
            cols.append(f'n{i}-uri')
            cols.append(f'n{i}-role')
            cols.append(f'n{i}-term')
            cols.append(f'n{i}-on_quorum_net')
            cols.append(f'n{i}-last_index')
            cols.append(f'n{i}-last_term')
            cols.append(f'n{i}-commit_index')
            cols.append(f'n{i}-leader_uri')
            cols.append(f'n{i}-voted_for')
            cols.append(f'n{i}-is_crashed')
        csv_lines = [cols,]
        for line in self.trace_lines:
            cols = []
            for ns in line:
                if ns.save_event is not None:
                    cols.append(f'{ns.save_event}')
                    cols.append(str(ns.uri))
                    if ns.message_action:
                        cols.append(ns.message.sender)
                        cols.append(ns.message.receiver)
                        cols.append(str(ns.message_action))
                        cols.append(ns.message.code)
                        if ns.message.code == "append_entries":
                            cols.append(f'{len(ns.message.entries)}')
                            cols.append(f'{ns.message.commitIndex}')
                            cols.append('')
                            cols.append('')
                            if ns.elapsed_time:
                                cols.append(f'{ns.elapsed_time:8.8f}')
                            else:
                                cols.append('')
                        elif ns.message.code == "append_response":
                            cols.append('')
                            cols.append('')
                            cols.append(f'{ns.message.success}')
                            cols.append(f'{ns.message.maxIndex}')
                            if ns.elapsed_time:
                                cols.append(f'{ns.elapsed_time:8.8f}')
                            else:
                                cols.append('')
                        else:
                            cols.append('')
                            cols.append('')
                            cols.append('')
                            cols.append('')
                            cols.append('')
                    else:
                        cols.append('')
                        cols.append('')
                        cols.append('')
                        cols.append('')
                        cols.append('')
                        cols.append('')
                        cols.append('')
                        cols.append('')
                        cols.append('')
                    break
            for index,ns in enumerate(line):
                if f"mcpy://{index + 1}" != ns.uri:
                    raise Exception('damn')
                cols.append(ns.uri)
                cols.append(str(ns.role_name))
                cols.append(str(ns.term))
                cols.append(str(ns.on_quorum_net))
                if ns.log_rec is None:
                    cols.append('0')
                    cols.append('0')
                else:
                    cols.append(str(ns.log_rec.index))
                    cols.append(str(ns.log_rec.term))
                cols.append(str(ns.commit_index))
                cols.append(f'{ns.leader_id}')
                cols.append(f'{ns.voted_for}')
                cols.append(f'{ns.is_crashed}')
            csv_lines.append(cols)
        return csv_lines

    def old_wrap_table(self, start_pos):
        if start_pos not in self.table_wraps:
            # we don't have instructions from the test code, so we just
            # make it up
            try:
                full_name, tfile, test_name = get_current_test()
            except Exception:
                test_name = "not in test, name unknown"
            wrap =  TableWrap(start_pos=start_pos,
                               description=test_name)
        else:
            wrap = self.table_wraps[start_pos]

        wrap.lines = []
        wrap.lines.append(wrap)
        pos = start_pos + 1
        while pos < len(self.trace_lines):
            wrap.lines.append(self.trace_lines[pos])
            if pos == wrap.end_pos:
                return wrap
            if pos in self.table_wraps:
                # this pos is the start of another table
                # nobody called end for this table
                wrap.end_pos = pos - 1
                return wrap
            pos += 1
        wrap.end_pos = pos - 1
        return wrap

    def wrap_table(self, start_pos):
        wrap = None
        for pos, test_rec in self.test_recs.items():
            if pos <= start_pos:
                if start_pos in test_recs.wraps:
                    wrap = test_rec.wraps[start_pos]
                    break
        if wrap is None:
            raise Exception(f'start position {start_pos} not found in test_recs')
        wrap.lines = []
        wrap.lines.append(wrap)
        pos = start_pos + 1
        while pos < len(self.trace_lines):
            wrap.lines.append(self.trace_lines[pos])
            if pos == wrap.end_pos:
                return wrap
            if pos in self.table_wraps:
                # this pos is the start of another table
                # nobody called end for this table
                wrap.end_pos = pos - 1
                return wrap
            pos += 1
        wrap.end_pos = pos - 1
        return wrap

    def to_condensed_tables(self, include_index=False):
        tables = []
        table = self.wrap_table(0)
        table.count_nodes(self.trace_lines)
        tables.append(table)
        while table.end_pos + 1 < len(self.trace_lines):
            table = self.wrap_table(table.end_pos + 1)
            table.count_nodes(self.trace_lines)
            tables.append(table)

        def short_event(ns):
            choices = dict(ROLE_CHANGED="NEW ROLE",
                           MESSAGE_OP="MSG",
                           CRASHED="CRASH",
                           RECOVERED="RESTART",
                           NET_PARTITION="NETSPLIT",
                           PARTITION_HEALED="NETJOIN",
                           COMMAND_STARTED="CMD START",
                           COMMAND_FINISHED="CMD DONE",)
            if ns.save_event in choices:
                return choices[ns.save_event]
            return ns.save_event

        def message_to_trace(ns, message):
            if message.code == "append_entries":
                short_code = "ae"
            elif message.code == "append_response":
                short_code = "ae_reply"
            elif message.code == "request_vote":
                short_code = "poll"
            elif message.code == "request_vote_response":
                short_code = "vote"
            elif message.code == "pre_vote":
                short_code = "p_v_r"
            elif message.code == "pre_vote_response":
                short_code = "p_v"
            elif message.code == "membership_change":
                short_code = "m_c"
            elif message.code == "membership_change_response":
                short_code = "m_cr"
            elif message.code == "transfer_power":
                short_code = "t_p"
            elif message.code == "transfer_power_response":
                short_code = "t_pr"
            elif message.code == "snapshot":
                short_code = "sn"
            elif message.code == "snapshot_response":
                short_code = "snr"
            target = message.receiver.split("/")[-1]
            sender = message.sender.split("/")[-1]
            if message.sender == ns.uri:
                value = f' {short_code}+N-{target}'
            else:
                value = f' N-{sender}+{short_code}'
            if message.code == "append_entries":
                value += f" t-{message.term} i-{message.prevLogIndex} lt-{message.prevLogTerm}"
                value += f" e-{len(message.entries)} c-{message.commitIndex}"
            elif message.code in ("request_vote", "pre_vote"):
                value += f" t-{message.term} li-{message.prevLogIndex} lt-{message.prevLogTerm}"
            elif message.code == "append_response":
                value += f" ok-{message.success} mi-{message.maxIndex}"
            elif message.code in ("request_vote_response", "pre_vote_response"):
                value += f" yes-{message.vote} "
            elif message.code in ("membership_change", "membership_change_response"):
                value += f" op-{message.op} n-{message.target_uri} "
                if message.code == "membership_change_response":
                    value += f"ok-{message.ok} "
            elif message.code in ("transfer_power", "transfer_power_response"):
                value += f" i-{message.prevLogIndex}"
                if message.code == "transfer_power_response":
                    value += f" ok-{message.success} "
            elif message.code in ("snapshot", "snapshot_response"):
                value += f" i-{message.prevLogIndex}"
                if message.code == "snapshot_response":
                    value += f" s-{message.success} "
            else:
                raise Exception('no code for message type')
            return value

        for table in tables:
            table.condensed = rows = []
            cols = []
            if include_index:
                cols.append("idx")
            #cols.append('event') # node id, event_type
            start_line = self.trace_lines[table.start_pos]
            for index in range(table.max_nodes):
                cols.append(f' N-{index+1}')
                cols.append(f' N-{index+1}')  # # message type + sender/target, or action
                cols.append(f' N-{index+1}' )
            rows.append(cols)
            cols = []
            if include_index:
                cols.append("")
            #cols.append("node ")
            for index in range(table.max_nodes):
                cols.append(f' Role')
                cols.append(f' Op')
                cols.append(f' Delta')
            rows.append(cols)
            events_to_show = []
            for pos, line in enumerate(self.trace_lines[table.start_pos: table.end_pos + 1]):
                if pos == table.start_pos or pos == table.end_pos:
                    events_to_show.append((pos,line))
                    continue
                for index, ns in enumerate(line):
                    if ns.save_event is not None:
                        if ns.save_event == SaveEvent.message_op:
                            # we are only going to show the trace if the
                            # resender or receiver is a leader, and only if the
                            # condition is sent or handled
                            if ns.role_name == "LEADER" or ns.role_name  == "CANDIDATE" or True:
                                if ns.message_action in ("sent", "handled_in"):
                                    events_to_show.append((pos,line))
                        else:
                            events_to_show.append((pos, line))
            last_states = {}
            for subpos,line_spec in enumerate(events_to_show):
                pos,line = line_spec
                cols = []
                if include_index:
                    cols.append(f" {pos} ")
                # do the op event column
                #for index, ns in enumerate(line):
                    #if ns.save_event is not None:
                        #cols.append(f" N-{index+1} ")
                        #break
                # fix up any empty log records, it makes it clearer that something changed
                for index, ns in enumerate(line):
                    # do the role column
                    if ns.role_name == "FOLLOWER" or ns.role_name is None:
                        cols.append(' FLWR ')
                    elif ns.role_name == "CANDIDATE":
                        cols.append(' CNDI ')
                    elif ns.role_name == "LEADER":
                        cols.append(' LEAD ')
                    # do the op column
                    if ns.save_event is None:
                        cols.append('')
                    else:
                        if ns.save_event == SaveEvent.message_op:
                            if ns.message_action in ("sent", "handled_in"):
                                cols.append(message_to_trace(ns, ns.message))
                        else:
                            cols.append(f" {short_event(ns)} ")
                    # do the delta column
                    # see if state changed
                    if ns.log_rec is None:
                        # fake it up for comparisons
                        ns.log_rec = LogRec()

                    d_t = ""
                    d_lt = ""
                    d_li = ""
                    d_ci = ""
                    d_net = ""
                    if str(ns.save_event) == "PARTITION_HEALED" and subpos == 0:
                        # can happen if netjoin is first in table
                        # due to subtest calls
                        d_net = " n=1"
                    
                    if index not in last_states:
                        # it is possible that this ns adds a new node
                        last_states[index] = None
                    elif subpos > 0:
                        last = last_states.get(index, None)
                        if last is None:
                            last_states[index] = None
                        if ns.term != last.term:
                            d_t = f" t-{ns.term}"
                        if ns.log_rec.term != last.log_rec.term:
                            d_lt = f" lt-{ns.log_rec.term}"
                        if ns.log_rec.index != last.log_rec.index:
                            d_li = f" li-{ns.log_rec.index}"
                        if ns.commit_index != last.commit_index:
                            d_ci = f" ci-{ns.commit_index}"
                        if ns.on_quorum_net:
                            if not last.on_quorum_net:
                                d_net = " n=1"
                            else:
                                d_net = ""
                        else:

                            d_net = " n=2"
                    cols.append(d_t + d_lt + d_li + d_ci + d_net)
                    last_states[index] = ns
                rows.append(cols)
        return tables

    def save_preamble(self, prefix):
        full_name, tfile, test_name = get_current_test()
        x = full_name.split('::')
        test_file_path = Path(x[0])
        test_name = x[1]
        trace_dir = Path(Path(__file__).parent.parent.resolve(), "captures", "test_traces")
        trace_dir = Path(trace_dir, prefix, test_file_path.stem)
        if not trace_dir.exists():
            trace_dir.mkdir(parents=True)
        return trace_dir, test_name
    
    def save_org(self, partial=False):
        if len(self.trace_lines) == 0 or self.test_rec is None:
            return
        if partial:
            prefix = "no_legend_org"
            include_legend = False
        else:
            prefix = "org"
            include_legend = True
        trace_dir, test_name = self.save_preamble(prefix)
        trace_path = Path(trace_dir, test_name + ".org")
        TraceCondenser(self).condense()
        org_lines = OrgFormatter(self).format()
        if len(org_lines) > 0:
            with open(trace_path, 'w') as f:
                for line in org_lines:
                    f.write(line + "\n")

    def save_digest_csv(self):
        if len(self.trace_lines) == 0 or self.test_rec is None:
            return
        trace_dir, test_name = self.save_preamble("digest_csv")
        trace_path = Path(trace_dir, test_name + ".csv")
        org_lines = self.to_condensed_org(include_legend=False)
        if len(org_lines) > 0:
            with open(trace_path, 'w') as f:
                for line in org_lines:
                    tmp = line.strip("|").split("|")
                    # this test is pretty fuzzy might fail, but
                    # it is hard to know how many columns there are
                    if len(tmp) < 2:
                        continue
                    new_line = ",".join(tmp)
                    f.write(new_line + "\n")

    def save_csv(self):
        if len(self.trace_lines) == 0 or self.test_rec is None:
            return
        trace_dir, test_name = self.save_preamble("csv")
        trace_path = Path(trace_dir, test_name + ".csv")
        csv_lines = self.to_csv()
        if len(csv_lines) > 1:
            with open(trace_path, 'w') as f:
                for line in csv_lines:
                    outline = ','.join(line)
                    f.write(outline + "\n")

    def save_rst(self):
        if len(self.trace_lines) == 0 or self.test_rec is None:
            return
        trace_dir, test_name = self.save_preamble("rst")
        trace_path = Path(trace_dir, test_name + ".rst")
        TraceCondenser(self).condense()
        rst_lines = RstFormatter(self).format()
        if len(rst_lines) > 0:
            with open(trace_path, 'w') as f:
                for line in rst_lines:
                    f.write(line + "\n")

class OrgFormatter:

    def __init__(self, trace):
        self.trace = trace
        self.test_rec  = trace.test_rec
        if self.test_rec.condensed_tables is None:
            raise Exception('Call trace condeser first!')

    def format(self, include_legend=True):
        tables = self.test_rec.condensed_tables
        all_rows = []
        all_rows.append(f"* Test {self.test_rec.test_name} from file {self.test_rec.test_path}")
        all_rows.append("")
        all_rows.append(self.test_rec.test_doc_string)
        all_rows.append("")
        if len(self.test_rec.used_raft) > 0 or len(self.test_rec.focused_raft) > 0:
            tf = TestFeatures(self.test_rec.test_name)
            for used in self.test_rec.used_raft:
                tf.add_used(used)
            for focused in self.test_rec.focused_raft:
                tf.add_focused(focused)
            for row in tf.org_format():
                all_rows.append(row)
        if include_legend:
            all_rows.append("")
            all_rows.append(" *[[condensed Trace Table Legend][Table legend]] located after last table in file*")
            all_rows.append("")

        for t_index, table in enumerate(tables):
            max_chars = 0
            # get the column widths
            row0 = table.condensed[0]
            col_widths = [0 for col in row0 ]
            trows = []
            for row in table.condensed:
                for col_index, col in enumerate(row):
                    col_widths[col_index] = max(col_widths[col_index], len(str(col)))
            trows.append(f"** {table.description}")
            for row in table.condensed:
                str_line = "| "
                for col_index, col in enumerate(row):
                    str_line += f"{col:{col_widths[col_index]}s} |"
                trows.append(str_line)
                max_chars = max(max_chars, len(str_line))
            trows.append('-' * max_chars)
            final_rows = [trows[0],]
            final_rows.append('-' * max_chars)
            final_rows.extend(trows[1:])
            all_rows.extend(final_rows)
            if False:
                for trow in final_rows:
                    print(trow)
        if include_legend:
            legend_path = Path(Path(__file__).parent, "table_legend.org")
            with open(legend_path, 'r') as f:
                buff = f.read()
            for lline in buff.split('\n'):
                all_rows.append(lline)
        return all_rows

class RstFormatter:

    def __init__(self, trace):
        self.trace = trace
        self.test_rec  = trace.test_rec
        if self.test_rec.condensed_tables is None:
            raise Exception('Call trace condeser first!')

    def format(self, include_legend=True):
        tables = self.test_rec.condensed_tables
        all_rows = []
        all_rows.append(f".. _{self.test_rec.test_name}:")
        all_rows.append("")
        s1 = f"Test {self.test_rec.test_name} from file {self.test_rec.test_path}"
        all_rows.append(s1)
        all_rows.append("="*len(s1))
        all_rows.append("")
        all_rows.append(self.test_rec.test_doc_string)
        all_rows.append("")
        if len(self.test_rec.used_raft) > 0 or len(self.test_rec.focused_raft) > 0:
            tf = TestFeatures(self.test_rec.test_name)
            for used in self.test_rec.used_raft:
                tf.add_used(used)
            for focused in self.test_rec.focused_raft:
                tf.add_focused(focused)
            for row in tf.rst_format():
                all_rows.append(row)
        if include_legend:
            all_rows.append("")
            all_rows.append("- See :ref:`Trace Table Legend` for help interpreting table contents")
            all_rows.append("")

        for t_index, table in enumerate(tables):
            max_chars = 0
            # get the column widths
            row0 = table.condensed[0]
            col_widths = [0 for col in row0 ]
            for row in table.condensed:
                for col_index, col in enumerate(row):
                    this_width =  len(str(col))
                    col_widths[col_index] = max(col_widths[col_index], this_width)
            
            all_rows.append(f"{table.description}".rstrip('\n'))
            all_rows.append("_"*len(table.description))
            all_rows.append("")
            trows = []
            liner = "+-"
            for cindex, cwidth in enumerate(col_widths):
                liner += "-"*(cwidth+1)
                liner += "+"
            divider = "+="
            for cindex, cwidth in enumerate(col_widths):
                divider += "="*(cwidth+1)
                divider += "+"
            for row in table.condensed:
                str_line = "| "
                for col_index, col in enumerate(row):
                    str_line += f"{col:{col_widths[col_index]}s} |"
                trows.append(str_line)
                max_chars = max(max_chars, len(str_line))
            for index, row in enumerate(trows):
                if index == 1:
                    all_rows.append(divider)
                else:
                    all_rows.append(liner)
                all_rows.append(row)
            all_rows.append("")
        return all_rows

class TraceCondenser:

    def __init__(self, trace):
        self.trace = trace

    def condense(self, include_index=False):
        tables = []
        test_rec = self.trace.test_rec
    
        table = test_rec.wraps[0]
        table.count_nodes(self.trace.trace_lines)
        tables.append(table)
        while table.end_pos + 1 < len(self.trace.trace_lines):
            table = test_rec.wraps[table.end_pos + 1]
            table.count_nodes(self.trace.trace_lines)
            tables.append(table)
            if table.end_pos is None:
                # never called end, common
                table.end_pos = len(self.trace.trace_lines)
                break

        def short_event(ns):
            choices = dict(ROLE_CHANGED="NEW ROLE",
                           MESSAGE_OP="MSG",
                           CRASHED="CRASH",
                           RECOVERED="RESTART",
                           NET_PARTITION="NETSPLIT",
                           PARTITION_HEALED="NETJOIN",
                           COMMAND_STARTED="CMD START",
                           COMMAND_FINISHED="CMD DONE",)
            if ns.save_event in choices:
                return choices[ns.save_event]
            return ns.save_event

        def message_to_trace(ns, message):
            if message.code == "append_entries":
                short_code = "ae"
            elif message.code == "append_response":
                short_code = "ae_reply"
            elif message.code == "request_vote":
                short_code = "poll"
            elif message.code == "request_vote_response":
                short_code = "vote"
            elif message.code == "pre_vote":
                short_code = "p_v_r"
            elif message.code == "pre_vote_response":
                short_code = "p_v"
            elif message.code == "membership_change":
                short_code = "m_c"
            elif message.code == "membership_change_response":
                short_code = "m_cr"
            elif message.code == "transfer_power":
                short_code = "t_p"
            elif message.code == "transfer_power_response":
                short_code = "t_pr"
            elif message.code == "snapshot":
                short_code = "sn"
            elif message.code == "snapshot_response":
                short_code = "snr"
            target = message.receiver.split("/")[-1]
            sender = message.sender.split("/")[-1]
            if message.sender == ns.uri:
                value = f' {short_code}+N-{target}'
            else:
                value = f' N-{sender}+{short_code}'
            if message.code == "append_entries":
                value += f" t-{message.term} i-{message.prevLogIndex} lt-{message.prevLogTerm}"
                value += f" e-{len(message.entries)} c-{message.commitIndex}"
            elif message.code in ("request_vote", "pre_vote"):
                value += f" t-{message.term} li-{message.prevLogIndex} lt-{message.prevLogTerm}"
            elif message.code == "append_response":
                value += f" ok-{message.success} mi-{message.maxIndex}"
            elif message.code in ("request_vote_response", "pre_vote_response"):
                value += f" yes-{message.vote} "
            elif message.code in ("membership_change", "membership_change_response"):
                value += f" op-{message.op} n-{message.target_uri} "
                if message.code == "membership_change_response":
                    value += f"ok-{message.ok} "
            elif message.code in ("transfer_power", "transfer_power_response"):
                value += f" i-{message.prevLogIndex}"
                if message.code == "transfer_power_response":
                    value += f" ok-{message.success} "
            elif message.code in ("snapshot", "snapshot_response"):
                value += f" i-{message.prevLogIndex}"
                if message.code == "snapshot_response":
                    value += f" s-{message.success} "
            else:
                raise Exception('no code for message type')
            return value

        for table in tables:
            table.condensed = rows = []
            cols = []
            if include_index:
                cols.append("idx")
            #cols.append('event') # node id, event_type
            start_line = self.trace.trace_lines[table.start_pos]
            for index in range(table.max_nodes):
                cols.append(f' N-{index+1}')
                cols.append(f' N-{index+1}')  # # message type + sender/target, or action
                cols.append(f' N-{index+1}' )
            rows.append(cols)
            cols = []
            if include_index:
                cols.append("")
            #cols.append("node ")
            for index in range(table.max_nodes):
                cols.append(f' Role')
                cols.append(f' Op')
                cols.append(f' Delta')
            rows.append(cols)
            events_to_show = []
            for pos, line in enumerate(self.trace.trace_lines[table.start_pos: table.end_pos + 1]):
                if pos == table.start_pos or pos == table.end_pos:
                    events_to_show.append((pos,line))
                    continue
                for index, ns in enumerate(line):
                    if ns.save_event is not None:
                        if ns.save_event == SaveEvent.message_op:
                            # we are only going to show the trace if the
                            # resender or receiver is a leader, and only if the
                            # condition is sent or handled
                            if ns.role_name == "LEADER" or ns.role_name  == "CANDIDATE" or True:
                                if ns.message_action in ("sent", "handled_in"):
                                    events_to_show.append((pos,line))
                        else:
                            events_to_show.append((pos, line))
            last_states = {}
            for subpos,line_spec in enumerate(events_to_show):
                pos,line = line_spec
                cols = []
                if include_index:
                    cols.append(f" {pos} ")
                # do the op event column
                #for index, ns in enumerate(line):
                    #if ns.save_event is not None:
                        #cols.append(f" N-{index+1} ")
                        #break
                # fix up any empty log records, it makes it clearer that something changed
                for index, ns in enumerate(line):
                    # do the role column
                    if ns.role_name == "FOLLOWER" or ns.role_name is None:
                        cols.append(' FLWR ')
                    elif ns.role_name == "CANDIDATE":
                        cols.append(' CNDI ')
                    elif ns.role_name == "LEADER":
                        cols.append(' LEAD ')
                    # do the op column
                    if ns.save_event is None:
                        cols.append('')
                    else:
                        if ns.save_event == SaveEvent.message_op:
                            if ns.message_action in ("sent", "handled_in"):
                                cols.append(message_to_trace(ns, ns.message))
                        else:
                            cols.append(f" {short_event(ns)} ")
                    # do the delta column
                    # see if state changed
                    if ns.log_rec is None:
                        # fake it up for comparisons
                        ns.log_rec = LogRec()

                    d_t = ""
                    d_lt = ""
                    d_li = ""
                    d_ci = ""
                    d_net = ""
                    if str(ns.save_event) == "PARTITION_HEALED" and subpos == 0:
                        # can happen if netjoin is first in table
                        # due to subtest calls
                        d_net = " n=1"
                    
                    if index not in last_states:
                        # it is possible that this ns adds a new node
                        last_states[index] = None
                    elif subpos > 0:
                        last = last_states.get(index, None)
                        if last is None:
                            last_states[index] = None
                        if ns.term != last.term:
                            d_t = f" t-{ns.term}"
                        if ns.log_rec.term != last.log_rec.term:
                            d_lt = f" lt-{ns.log_rec.term}"
                        if ns.log_rec.index != last.log_rec.index:
                            d_li = f" li-{ns.log_rec.index}"
                        if ns.commit_index != last.commit_index:
                            d_ci = f" ci-{ns.commit_index}"
                        if ns.on_quorum_net:
                            if not last.on_quorum_net:
                                d_net = " n=1"
                            else:
                                d_net = ""
                        else:

                            d_net = " n=2"
                    cols.append(d_t + d_lt + d_li + d_ci + d_net)
                    last_states[index] = ns
                rows.append(cols)
        test_rec.condensed_tables = tables

    def wrap_table(self, start_pos):
        wrap = None
        test_rec = self.trace.test_rec
        if start_pos not in test_rec.wraps:
            raise Exception(f'start position {start_pos} not found in test_rec')
        wrap = test_rec.wraps[start_pos]
        wrap.lines = []
        wrap.lines.append(wrap)
        pos = start_pos + 1
        while pos < len(self.trace.trace_lines):
            wrap.lines.append(self.trace.trace_lines[pos])
            if pos == wrap.end_pos:
                return wrap
            if pos in test_rec.wraps:
                # this pos is the start of another table
                # nobody called end for this table
                wrap.end_pos = pos - 1
                return wrap
            pos += 1
        wrap.end_pos = pos - 1
        return wrap

