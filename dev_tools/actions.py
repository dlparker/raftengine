from dev_utils.cluster_states import ActionCode, RoleCode

class MessagePromise:

    def __init__(self, code:MessageCode, source:str, target:str):
        self.code = code,
        self.source = source
        self.target = target
        
    
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
            return False

        for o_node in change_proposal.start_state.nodes:
            if o_node.node_uri == node.uri:
                continue
            prom = MessagePromise(MessageCode.request_vote, node.node_uri, o_node.node_uri)
            change_proposal.push_message_promise(prom)
        return True

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
            return False
        return True

    def generate_step(self, change_def, change_proposal):
        node = change_proposal.get_node_start(change_def.uri)
        res = []
        res.append('cmd = DoNow(ActionCode.run_command, "{change_def.value}")')
        res.append('ps = PhaseStep("{node.uri}", do_now_class=cmd)')
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
            
                                              
