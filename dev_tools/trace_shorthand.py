import json
from raftengine.api.log_api import LogRec
from dev_tools.trace_data import SaveEvent, decode_message

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
                # Pass node_state to message formatter for directional formatting
                try:
                    # Try to pass node_state for formatters that need it
                    formatter = mf(self.node_state.message, self.node_state)
                except TypeError:
                    # Fallback for formatters that don't accept node_state
                    formatter = mf(self.node_state.message)
                self.op = formatter.format()
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
        # Register all message formatters
        self.message_formatter_map['append_entries'] = AppendEntriesShortestFormat
        self.message_formatter_map['append_response'] = AppendResponseShortestFormat
        self.message_formatter_map['request_vote'] = RequestVoteShortestFormat
        self.message_formatter_map['request_vote_response'] = RequestVoteResponseShortestFormat
        self.message_formatter_map['pre_vote'] = PreVoteShortestFormat
        self.message_formatter_map['pre_vote_response'] = PreVoteResponseShortestFormat
        self.message_formatter_map['membership_change'] = MembershipChangeShortestFormat
        self.message_formatter_map['membership_change_response'] = MembershipChangeResponseShortestFormat
        self.message_formatter_map['transfer_power'] = TransferPowerShortestFormat
        self.message_formatter_map['transfer_power_response'] = TransferPowerResponseShortestFormat
        self.message_formatter_map['snapshot'] = SnapshotShortestFormat
        self.message_formatter_map['snapshot_response'] = SnapshotResponseShortestFormat

    def shorten_role(self):
        """Convert role to shortened form like ShorthandType1.shorten_role"""
        if self.node_state.role_name == "FOLLOWER":
            return 'FLWR'
        elif self.node_state.role_name == "CANDIDATE":
            return 'CNDI'
        elif self.node_state.role_name == "LEADER":
            return 'LEAD'
        return 'FLWR'

    def prep_format(self):
        """Override to use shortened role and legacy-style delta format"""
        # Use shortened role
        self.role = self.shorten_role()
        
        # Handle op field - messages use formatters, other events use short_event
        self.op = None
        if self.node_state.save_event:
            if self.node_state.save_event == SaveEvent.message_op:
                if self.node_state.message:
                    if isinstance(self.node_state.message, dict):
                        code = self.node_state.message['code']
                    else:
                        code = self.node_state.message.code
                    mf = self.message_formatter_map.get(code, self.message_formatter_map['default'])
                    # Pass node_state to message formatter for directional formatting
                    try:
                        # Try to pass node_state for formatters that need it
                        formatter = mf(self.node_state.message, self.node_state)
                    except TypeError:
                        # Fallback for formatters that don't accept node_state
                        formatter = mf(self.node_state.message)
                    self.op = formatter.format()
            else:
                self.op = self.short_event(self.node_state)
        
        # Build delta using exact legacy logic from Shorthand.shorten_node_states
        self.delta = self.build_legacy_delta()
        
        result = dict(role=self.role,
                      op=self.op,
                      delta=self.delta)
        return result

    def build_legacy_delta(self):
        """Build delta dictionary using exact logic from Shorthand.shorten_node_states"""
        from raftengine.api.log_api import LogRec
        
        # Initialize delta values (empty strings by default)
        d_t = ""
        d_lt = ""
        d_li = ""
        d_ci = ""
        d_net = ""
        
        # Handle fake log_rec if None (copied from legacy code)
        if self.node_state.log_rec is None:
            self.node_state.log_rec = LogRec()
        
        # Special case: PARTITION_HEALED at first position (pos == 0)
        # Since we don't have position context, we'll check if it's PARTITION_HEALED and no prev_state
        if str(self.node_state.save_event) == "PARTITION_HEALED" and self.prev_state is None:
            d_net = self.shorten_net_id(1)
        
        # Only calculate deltas if we have a previous state
        if self.prev_state is not None:
            # Handle case where prev_state might not have log_rec
            if self.prev_state.log_rec is None:
                self.prev_state.log_rec = LogRec()
            
            if self.node_state.term != self.prev_state.term:
                d_t = self.shorten_term(self.node_state)
            if self.node_state.log_rec.term != self.prev_state.log_rec.term:
                d_lt = self.shorten_rec_term(self.node_state)
            if self.node_state.log_rec.index != self.prev_state.log_rec.index:
                d_li = self.shorten_rec_index(self.node_state)
            if self.node_state.commit_index != self.prev_state.commit_index:
                d_ci = self.shorten_commit_index(self.node_state)
            
            # Network state logic
            if self.node_state.on_quorum_net:
                if not self.prev_state.on_quorum_net:
                    d_net = self.shorten_net_id(1)
            else:
                d_net = self.shorten_net_id(2)
        
        # Build dictionary with legacy-style keys and values
        delta_dict = {
            "term": d_t,
            "log_last_term": d_lt, 
            "last_index": d_li,
            "commit_index": d_ci,
            "network_id": d_net
        }
        
        return delta_dict

    @classmethod
    def short_event(cls, ns):
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

    @classmethod
    def shorten_term(cls, ns):
        return f"t-{ns.term}"

    @classmethod
    def shorten_rec_term(cls, ns):
        return f"lt-{ns.log_rec.term}"

    @classmethod
    def shorten_rec_index(cls, ns):
        return f"li-{ns.log_rec.index}"

    @classmethod
    def shorten_commit_index(cls, ns):
        return f"ci-{ns.commit_index}"

    @classmethod
    def shorten_net_id(cls, nid):
        return f"n={nid}"
    
    def format(self):
        """Return formatted data as dictionary"""
        return self.prep_format()
    
    def format_json(self):
        """Return formatted data as JSON string (backwards compatibility)"""
        return json.dumps(self.format())
        
class AppendEntriesShortestFormat(MessageFormat):

    def __init__(self, inmessage, node_state=None):
        super().__init__(inmessage)
        if self.message.code != "append_entries":
            raise Exception(f'not an append_entries message {str(self.message)}')
        self.node_state = node_state

    def format(self):
        short_code = "ae"
        target = self.message.receiver.split("/")[-1]
        sender = self.message.sender.split("/")[-1]
        
        if self.node_state and self.message.sender == self.node_state.uri:
            value = f'{short_code}+N-{target}'
        else:
            value = f'N-{sender}+{short_code}'
        value += f" t-{self.message.term} i-{self.message.prevLogIndex} lt-{self.message.prevLogTerm}"
        value += f" e-{len(self.message.entries)} c-{self.message.commitIndex}"
        return value

class AppendResponseShortestFormat(MessageFormat):

    def __init__(self, inmessage):
        super().__init__(inmessage)
        if self.message.code != "append_response":
            raise Exception(f'not an append_response message {str(self.message)}')

    def format(self):
        # Use same logic as ShorthandType1.message_to_trace for append_response
        short_code = "ae_reply"
        target = self.message.receiver.split("/")[-1]
        sender = self.message.sender.split("/")[-1]
        
        # For append_response, we always show incoming messages (N-sender+code)
        value = f'N-{sender}+{short_code}'
        value += f" ok-{self.message.success} mi-{self.message.maxIndex}"
        return value

class RequestVoteShortestFormat(MessageFormat):

    def __init__(self, inmessage, node_state=None):
        super().__init__(inmessage)
        if self.message.code != "request_vote":
            raise Exception(f'not a request_vote message {str(self.message)}')
        self.node_state = node_state

    def format(self):
        short_code = "poll"
        target = self.message.receiver.split("/")[-1]
        sender = self.message.sender.split("/")[-1]
        
        if self.node_state and self.message.sender == self.node_state.uri:
            value = f'{short_code}+N-{target}'
        else:
            value = f'N-{sender}+{short_code}'
        value += f" t-{self.message.term} li-{self.message.prevLogIndex} lt-{self.message.prevLogTerm}"
        return value

class RequestVoteResponseShortestFormat(MessageFormat):

    def __init__(self, inmessage, node_state=None):
        super().__init__(inmessage)
        if self.message.code != "request_vote_response":
            raise Exception(f'not a request_vote_response message {str(self.message)}')
        self.node_state = node_state

    def format(self):
        short_code = "vote"
        target = self.message.receiver.split("/")[-1]
        sender = self.message.sender.split("/")[-1]
        
        if self.node_state and self.message.sender == self.node_state.uri:
            value = f'{short_code}+N-{target}'
        else:
            value = f'N-{sender}+{short_code}'
        value += f" yes-{self.message.vote}"
        return value

class PreVoteShortestFormat(MessageFormat):

    def __init__(self, inmessage, node_state=None):
        super().__init__(inmessage)
        if self.message.code != "pre_vote":
            raise Exception(f'not a pre_vote message {str(self.message)}')
        self.node_state = node_state

    def format(self):
        short_code = "p_v_r"
        target = self.message.receiver.split("/")[-1]
        sender = self.message.sender.split("/")[-1]
        
        if self.node_state and self.message.sender == self.node_state.uri:
            value = f'{short_code}+N-{target}'
        else:
            value = f'N-{sender}+{short_code}'
        value += f" t-{self.message.term} li-{self.message.prevLogIndex} lt-{self.message.prevLogTerm}"
        return value

class PreVoteResponseShortestFormat(MessageFormat):

    def __init__(self, inmessage, node_state=None):
        super().__init__(inmessage)
        if self.message.code != "pre_vote_response":
            raise Exception(f'not a pre_vote_response message {str(self.message)}')
        self.node_state = node_state

    def format(self):
        short_code = "p_v"
        target = self.message.receiver.split("/")[-1]
        sender = self.message.sender.split("/")[-1]
        
        if self.node_state and self.message.sender == self.node_state.uri:
            value = f'{short_code}+N-{target}'
        else:
            value = f'N-{sender}+{short_code}'
        value += f" yes-{self.message.vote}"
        return value

class MembershipChangeShortestFormat(MessageFormat):

    def __init__(self, inmessage, node_state=None):
        super().__init__(inmessage)
        if self.message.code != "membership_change":
            raise Exception(f'not a membership_change message {str(self.message)}')
        self.node_state = node_state

    def format(self):
        short_code = "m_c"
        target = self.message.receiver.split("/")[-1]
        sender = self.message.sender.split("/")[-1]
        
        if self.node_state and self.message.sender == self.node_state.uri:
            value = f'{short_code}+N-{target}'
        else:
            value = f'N-{sender}+{short_code}'
        value += f" op-{self.message.op} n-{self.message.target_uri}"
        return value

class MembershipChangeResponseShortestFormat(MessageFormat):

    def __init__(self, inmessage, node_state=None):
        super().__init__(inmessage)
        if self.message.code != "membership_change_response":
            raise Exception(f'not a membership_change_response message {str(self.message)}')
        self.node_state = node_state

    def format(self):
        short_code = "m_cr"
        target = self.message.receiver.split("/")[-1]
        sender = self.message.sender.split("/")[-1]
        
        if self.node_state and self.message.sender == self.node_state.uri:
            value = f'{short_code}+N-{target}'
        else:
            value = f'N-{sender}+{short_code}'
        value += f" op-{self.message.op} n-{self.message.target_uri} ok-{self.message.ok}"
        return value

class TransferPowerShortestFormat(MessageFormat):

    def __init__(self, inmessage, node_state=None):
        super().__init__(inmessage)
        if self.message.code != "transfer_power":
            raise Exception(f'not a transfer_power message {str(self.message)}')
        self.node_state = node_state

    def format(self):
        short_code = "t_p"
        target = self.message.receiver.split("/")[-1]
        sender = self.message.sender.split("/")[-1]
        
        if self.node_state and self.message.sender == self.node_state.uri:
            value = f'{short_code}+N-{target}'
        else:
            value = f'N-{sender}+{short_code}'
        value += f" i-{self.message.prevLogIndex}"
        return value

class TransferPowerResponseShortestFormat(MessageFormat):

    def __init__(self, inmessage, node_state=None):
        super().__init__(inmessage)
        if self.message.code != "transfer_power_response":
            raise Exception(f'not a transfer_power_response message {str(self.message)}')
        self.node_state = node_state

    def format(self):
        short_code = "t_pr"
        target = self.message.receiver.split("/")[-1]
        sender = self.message.sender.split("/")[-1]
        
        if self.node_state and self.message.sender == self.node_state.uri:
            value = f'{short_code}+N-{target}'
        else:
            value = f'N-{sender}+{short_code}'
        value += f" i-{self.message.prevLogIndex} ok-{self.message.success}"
        return value

class SnapshotShortestFormat(MessageFormat):

    def __init__(self, inmessage, node_state=None):
        super().__init__(inmessage)
        if self.message.code != "snapshot":
            raise Exception(f'not a snapshot message {str(self.message)}')
        self.node_state = node_state

    def format(self):
        short_code = "sn"
        target = self.message.receiver.split("/")[-1]
        sender = self.message.sender.split("/")[-1]
        
        if self.node_state and self.message.sender == self.node_state.uri:
            value = f'{short_code}+N-{target}'
        else:
            value = f'N-{sender}+{short_code}'
        value += f" i-{self.message.prevLogIndex}"
        return value

class SnapshotResponseShortestFormat(MessageFormat):

    def __init__(self, inmessage, node_state=None):
        super().__init__(inmessage)
        if self.message.code != "snapshot_response":
            raise Exception(f'not a snapshot_response message {str(self.message)}')
        self.node_state = node_state

    def format(self):
        short_code = "snr"
        target = self.message.receiver.split("/")[-1]
        sender = self.message.sender.split("/")[-1]
        
        if self.node_state and self.message.sender == self.node_state.uri:
            value = f'{short_code}+N-{target}'
        else:
            value = f'N-{sender}+{short_code}'
        value += f" i-{self.message.prevLogIndex} s-{self.message.success}"
        return value


