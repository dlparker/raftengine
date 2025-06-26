import json
from raftengine.api.log_api import LogRec
from dev_tools.trace_data import SaveEvent, decode_message

class Shorthand:
    """Turns lists of NodeState objects into string versions of the data"""
    
    def __init__(self, test_section, filtered_lines):
        self.test_section = test_section
        self.lines = filtered_lines
        
    def shorten_node_states(self, shtype):
        """Format node states into condensed table rows"""
        rows = []
        cols = []
        last_states = {}
        for pos, line in enumerate(self.lines):
            cols = []
            # fix up any empty log records, it makes it clearer that something changed
            for index, ns in enumerate(line):
                cols.append(shtype.shorten_role(ns))
                # do the op column
                if ns.save_event is None:
                    cols.append('')
                else:
                    if ns.save_event == SaveEvent.message_op:
                        if ns.message_action in ("sent", "handled_in"):
                            cols.append(shtype.message_to_trace(ns, ns.message))
                        else:
                            cols.append('')
                    else:
                        cols.append(f"{shtype.short_event(ns)}")
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
                if str(ns.save_event) == "PARTITION_HEALED" and pos == 0:
                    # can happen if netjoin is first in table
                    # due to subtest calls
                    d_net = shtype.shorten_net_id(1)
                
                if index not in last_states:
                    # it is possible that this ns adds a new node
                    last_states[index] = None
                elif pos > 0:
                    last = last_states.get(index, None)
                    if last is None:
                        last_states[index] = None
                    if ns.term != last.term:
                        d_t = shtype.shorten_term(ns)
                    if ns.log_rec.term != last.log_rec.term:
                        d_lt = shtype.shorten_rec_term(ns)
                    if ns.log_rec.index != last.log_rec.index:
                        d_li = shtype.shorten_rec_index(ns)
                    if ns.commit_index != last.commit_index:
                        d_ci = shtype.shorten_commit_index(ns)
                    if ns.on_quorum_net:
                        if not last.on_quorum_net:
                            d_net = shtype.shorten_net_id(1)
                    else:
                        d_net = shtype.shorten_net_id(2)
                cols.append(shtype.format_log_list([d_t, d_lt, d_li, d_ci, d_net]))
                last_states[index] = ns
            rows.append(cols)
        return rows


class ShorthandType1:
    
    @staticmethod
    def short_event(ns):
        """Convert save_event to short string representation"""
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

    @staticmethod
    def format_log_list(log_list):
        res = ''
        for item in log_list:
            if item.strip() != '':
                res += item
                res += " "
        return res.rstrip(' ')
    
    @staticmethod
    def message_to_trace(ns, inmessage):
        if isinstance(inmessage, dict):
            message = decode_message(inmessage)
        else:
            message = inmessage
        """Convert message to trace string representation"""
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
            value = f'{short_code}+N-{target}'
        else:
            value = f'N-{sender}+{short_code}'
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

    @staticmethod
    def shorten_role(ns):
        if ns.role_name == "FOLLOWER":
            return 'FLWR'
        elif ns.role_name == "CANDIDATE":
            return 'CNDI'
        elif ns.role_name == "LEADER":
            return 'LEAD'
        return 'FLWR'

    @staticmethod
    def shorten_term(ns):
        return f"t-{ns.term}"

    @staticmethod
    def shorten_rec_term(ns):
        return f"lt-{ns.log_rec.term}"

    @staticmethod
    def shorten_rec_index(ns):
        return f"li-{ns.log_rec.index}"

    @staticmethod
    def shorten_commit_index(ns):
        return f"ci-{ns.commit_index}"

    @staticmethod
    def shorten_net_id(nid):
        return f"n={nid}"

class MessageFormat:

    def __init__(self, inmessage):
        if isinstance(inmessage, dict):
            self.message = decode_message(inmessage)
        else:
            self.message = inmessage

    def prep_format(self):
        return self.message.__dict__
                  
    def format(self):
        return str(self.message)

class NodeStateFormat:

    def __init__(self, node_state, prev_state=None):
        self.node_state = node_state
        self.prev_state = prev_state
        self.role = None
        self.op = None
        self.delta = None
        self.message_formatter_map = {}
        self.message_formatter_map['default'] = MessageFormat

    def prep_format(self):
        self.role = self.node_state.role_name
        if self.node_state.save_event:
            self.op = self.node_state.save_event
            if self.node_state.message:
                if isinstance(self.node_state.message, dict):
                    code = self.node_state.message['code']
                else:
                    code = self.node_state.message.code
                mf = self.message_formatter_map.get(code, self.message_formatter_map['default'])
                self.op = mf(self.node_state.message).format()
        self.delta = {}
        if self.node_state.log_rec:
            log_state  = dict(last_index=self.node_state.log_rec.index,
                              last_term=self.node_state.log_rec.term,
                              term=self.node_state.term,
                              commit_index=self.node_state.commit_index,
                              leader_id= self.node_state.leader_id)
            if self.prev_state and self.prev_state.log_rec:
                prev_log_state = dict(last_index=self.prev_state.log_rec.index,
                                      last_term=self.prev_state.log_rec.term,
                                      term=self.prev_state.term,
                                      commit_index=self.prev_state.commit_index,
                                      leader_id= self.prev_state.leader_id)
                for key in [key for key in log_state if log_state[key] != prev_log_state[key]]:
                    self.delta[key] = log_state[key]
            else:
                self.delta = log_state
        result = dict(role=self.role,
                      op=self.op,
                      delta=self.delta)
        return result
        
    def format(self):
        data = self.prep_format()
        return json.dumps(data)
        

class NodeStateShortestFormat(NodeStateFormat):

    def __init__(self, node_state, prev_state=None):
        super().__init__(node_state, prev_state)
        self.message_formatter_map['append_entries'] = AppendEntriesShortestFormat

    def format(self):
        data = self.prep_format()
        return json.dumps(data)
        
class AppendEntriesShortestFormat(MessageFormat):

    def __init__(self, inmessage):
        super().__init__(inmessage)
        if self.message.code != "append_entries":
            raise Exception(f'not an append_entries message {str(self.message)}')

    def format(self):
        res = "ae"
        res += f" t-{self.message.term} i-{self.message.prevLogIndex} lt-{self.message.prevLogTerm}"
        res += f" e-{len(self.message.entries)} c-{self.message.commitIndex}"
        return res


