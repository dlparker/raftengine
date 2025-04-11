from dev_utils.cluster_states import ActionCode, RoleCode

class MessagePromise:

    def __init__(self, code:MessageCode, sender:str, target:str):
        self.code = code,
        self.sender = sender
        
    
class Action:

    def __init__(self, code:ActionCode, required_role=None):
        self.code = code
        self.required_role = required_role

class StartCampaign(Action):

    def __init__(self):
        super().__init__(ActionCode.start_campaign, required_role=RoleCode.follower)

    def can_apply(self, change_def, change_proposal):
        node = change_proposal.get_node_start(change_def.uri)
        # What does follower need before staring command? Anything?
        # Even things you might thnk it should check, it doesn't.
        # It just assumes all is fine until some node tells it
        # to F off.
        if node.role != RoleCode.follower:
            return False, f"Node must be follower, not {node.role}"

        for o_node in change_proposal.start_state.nodes:
            if o_node.node_uri == node.uri:
                continue
            prom = MessagePromise(code=MessageCode.request_vote, sender=node.node_uri, target=o_node.node_uri)
            change_proposal.push_message_promise(prom)
        return False, "Only requirement is that node must be follower, validated"

    def generate_phase(self, change_def, change_proposal):
        node = change_proposal.get_node_start(change_def.uri)
        res = []
        res.append("# This action causes stepper to use simulation control to ")
        res.append("# trigger the code that would run if the election_timeout ")
        res.append("# triggered. This results the targeted node incrementing its term")
        res.append("# an sending a broadcast of the RequestVote message.")
        res.append("# This action DOES NOT allow the flow of the actual messages.")
        res.append("start = DoNow(ActionCode.start_campaign)")
        res.append('ps = PhaseStep("{node.uri}", do_now_class=start)')
        res.append("")
        res.append("# All the other nodes do nothing for this phase")
        res.append("steps = []")
        for o_node in change_proposal.start_state.nodes:
            if o_node.node_uri == node.uri:
                continue
            res.append('steps.append(PhaseStep("{o_node.uri}", do_now_class=NoOp()))')
        res.append(f'desc = "Causes node {node.node_uri} to start a campaign to be leader, other nodes idle"')
        res.append('sequence.add_phase(Phase(steps), desc=desc)')
        return res

class VoteYes(Action):

    def __init__(self):
        super().__init__(ActionCode.vote_yes, required_role=RoleCode.follower)

    def can_apply(self, change_def, change_proposal):
        node = change_proposal.get_node_start(change_def.uri)
        if node.role != RoleCode.follower:
            return False, f"Node must be follower, not {node.role}"

        # To vote yes, follower needs an incoming vote request,
        # and the term in that request needs to be greater than
        # the log term, and the follower's voted for value needs
        # to None.
        vote_msg = change_proposal.claim_message(MessageCode.request_vote, target=node.node_uri)
        if not vote_msg:
            return False, f"Node has no pending vote_request message"

        if self.log_state.votedFor != vote_msg.sender:
            return False, f"Already voted for other this term"
            
        for o_node in change_proposal.start_state.nodes:
            if o_node.node_uri != vote_msg.sender:
                continue
            if o_node.log_state
            prom = MessagePromise(code=MessageCode.request_vote, sender=node.node_uri, target=o_node.node_uri)
            change_proposal.push_message_promise(prom)
        return False, "Only requirement is that node must be follower, validated"

    def generate_phase(self, change_def, change_proposal):
        node = change_proposal.get_node_start(change_def.uri)
        res = []
        res.append("# This action causes stepper to use simulation control to ")
        res.append("# trigger the code that would run if the election_timeout ")
        res.append("# triggered. This results the targeted node incrementing its term"
        res.append("# an sending a broadcast of the RequestVote message.")
        res.append("# This action DOES NOT allow the flow of the actual messages.")
        res.append("start = DoNow(ActionCode.start_campaign)")
        res.append('ps = PhaseStep("{node.uri}", do_now_class=start)')
        res.append("")
        res.append("# All the other nodes do nothing for this phase")
        res.append("steps = []")
        for o_node in change_proposal.start_state.nodes:
            if o_node.node_uri == node.uri:
                continue
            res.append('steps.append(PhaseStep("{o_node.uri}", do_now_class=NoOp()))')
        res.append(f'desc = "Causes node {node.node_uri} to start a campaign to be leader, other nodes idle"')
        res.append('sequence.add_phase(Phase(steps), desc=desc)')
        return res
    
    
class DoCommand(Action):

    def __init__(self):
        super().__init__(ActionCode.start_term, required_role=RoleCode.leader)

    def can_apply(self, change_def, change_proposal):
        node = change_proposal.get_node_start(change_def.uri)
        # What does leader need before staring command? Anything?
        # Even things you might thnk it should check, it doesn't.
        # It just assumes all is fine until some node tells it
        # to F off.
        if node.role != RoleCode.leader:
            return False, f"Node must be leader, not {node.role}"
        return False, "Only requirement is that node must be leader, validated"

    def generate_phase(self, change_def, change_proposal):
        node = change_proposal.get_node_start(change_def.uri)
        res = []
        res.append("# This action causes stepper send a command to the leader. ")
        res.append("# This results the leader saving the command in the log ")
        res.append("# and sending a broadcast of the AppendEntries message.")
        res.append("# This action DOES NOT allow the flow of the actual messages.")
        res.append('cmd = DoNow(ActionCode.run_command, "{change_def.value}")')
        res.append('ps = PhaseStep("{node.uri}", do_now_class=cmd)')
        res.append("")
        res.append("# All the other nodes do nothing for this phase")
        res.append("steps = []")
        for o_node in change_proposal.start_state.nodes:
            if o_node.node_uri == node.uri:
                continue
            res.append('steps.append(PhaseStep("{o_node.uri}", do_now_class=NoOp()))')
        res.append(f'desc = "Causes node {node.node_uri} to send command {change_def.value}"')
        res.append('sequence.add_phase(Phase(steps), desc=desc)')
        return res

class ChangeType(str, Enum):

    term_up = "TERM_UP"
    last_index_up = "LAST_INDEX_UP"
    last_term_up = "LAST_TERM_UP"
    commit_index_up = "COMMIT_INDEX_UP"
    net_split = "NET_SPLIT"
    net_heal = "NET_HEAL"
    msg_op = "MSG_OP"
    
    def __str__(self):
        return self.value

class ChangeDef:

    def __init__(self, node_uri, change_type:ChangeType, value=None):
        self.node_uri = node_uri
        self.change_type = change_type
        self.value = value
                 
class CompoundChangeDef(ChangeDef):

    def __init__(self, node_uri, change_type:ChangeType, value=None):
        super().__init__(node_uri, change_type, value)
        self.more = []

    def add_change_def(self, change_def:ChangDef):
        self.more.append(change_def)
                 
                 
class ChangeChain:

    def __init__(self):
        self.unlinked = []
        self.linked = []
        self.unlinked_messages = []
        self.unlinked_messages = []

    def new_link(self, change_def:ChangeDef):
        self.unlinked.append(change_def)
        
class ChangeProposal:

    def __init__(self, start_state, end_state):
        self.start_state = start_state
        self.end_state = end_state
        self.chain = ChangeChain()
        self.pairs = {}
        for s_node in start_state.nodes:
            for e_node in end_state.nodes:
            self.pairs[s_node.node_uri] = (s_node, e_node)

        for uri in self.pairs:
            (s_node, e_node) = self.pairs[uri]
            log_changes = []
            if e_node.log_state.term != s_node.log_state.term:
                log_changes.append(ChangeDef(uri, ChangeType.term_up, e_node.log_state.term - s_node.log_state.term))
            if e_node.log_state.last_index != s_node.log_state.last_index:
                log_changes.append(ChangeDef(uri, ChangeType.last_index_up, e_node.log_state.last_index - s_node.log_state.last_index))
            if e_node.log_state.commit_index != s_node.log_state.commit_index:
                log_changes.append(ChangeDef(uri, ChangeType.commit_index_up, e_node.log_state.commit_index - s_node.log_state.commit_index))
            if len(log_changes) > 0:
                first = log_changes[0]
                if len(log_changes) > 1:
                    cd = CompoundChangeDef(first.uri, first.change_type, first.value)
                    for other in log_change[1:]:
                        cd.add_change_def(other)
                else:
                    cd = first
                self.chain.new_link(cd)
            if e_node.network_mode != s_node.network_mode:
                if e_node.network_mode == NetworkMode.minority:
                    self.chain.new_link(ChangeDef(uri, ChangeType.net_split))
                else:
                    self.chain.new_link(ChangeDef(uri, ChangeType.net_heal))
            
                                              
