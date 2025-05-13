import os
from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

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

class TestTrace:

    def __init__(self, cluster):
        self.cluster = cluster
        self.node_states = {}
        self.trace_lines = []
        self.table_wraps = {}
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


    def start_subtest(self, description, test_path_str=None, test_doc_string=None):
        old_st = self.current_wrap
        if old_st and old_st.end_pos is None:
            old_st.end_pos=len(self.trace_lines)-1,
        st = TableWrap(start_pos=len(self.trace_lines),
                          description=description,
                          test_path=test_path_str,
                          test_doc_string=test_doc_string)
        self.current_wrap = st
        self.table_wraps[st.start_pos] = st

    def end_subtest(self):
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

    def wrap_table(self, start_pos):
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
                value = f' {short_code}->N-{target}'
            else:
                value = f' N-{sender}->{short_code}'
            if message.code == "append_entries":
                value += f" t={message.term} i={message.prevLogIndex} lt={message.prevLogTerm}"
                value += f" e={len(message.entries)} c={message.commitIndex}"
            elif message.code in ("request_vote", "pre_vote"):
                value += f" t={message.term} li={message.prevLogIndex} lt={message.prevLogTerm}"
            elif message.code == "append_response":
                value += f" ok={message.success} mi={message.maxIndex}"
            elif message.code in ("request_vote_response", "pre_vote_response"):
                value += f" yes={message.vote} "
            elif message.code in ("membership_change", "membership_change_response"):
                value += f" op={message.op} n={message.target_uri} "
                if message.code == "membership_change_response":
                    value += f"ok={message.ok} "
            elif message.code in ("transfer_power", "transfer_power_response"):
                value += f" i={message.prevLogIndex}"
                if message.code == "transfer_power_response":
                    value += "ok={message.success} "
            elif message.code in ("snapshot", "snapshot_response"):
                value += f" i={message.prevLogIndex}"
                if message.code == "snapshot_response":
                    value += "s={message.success} "
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
                            d_t = f" t={ns.term}"
                        if ns.log_rec.term != last.log_rec.term:
                            d_lt = f" lt={ns.log_rec.term}"
                        if ns.log_rec.index != last.log_rec.index:
                            d_li = f" li={ns.log_rec.index}"
                        if ns.commit_index != last.commit_index:
                            d_ci = f" ci={ns.commit_index}"
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



