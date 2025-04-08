import asyncio
from dataclasses import dataclass

from dev_tools.cluster_states import (NodeState, LogState, ActionOnState, ActionOnMessage,
                                      ValidateState, MessageCode, CommsOp, CommsEdge, ActionCode, Sequence, DoNow,
                                      PhaseStep, NoOp, Phase)
from dev_tools.servers import PausingCluster, PausingServer, PauseTrigger
from raftengine.messages.append_entries import AppendEntriesMessage, AppendResponseMessage
from raftengine.messages.request_vote import RequestVoteMessage, RequestVoteResponseMessage


@dataclass
class NodeRecord:
    orig_state: NodeState
    server: PausingServer

msg_code_map = {MessageCode.request_vote: RequestVoteMessage.code,
                MessageCode.request_vote_response: RequestVoteResponseMessage.code,
                MessageCode.append_entries: AppendEntriesMessage.code,
                MessageCode.append_entries_response: AppendResponseMessage.code}

class WhenMsgOp(PauseTrigger):

    def __init__(self, comms_op: CommsOp, total_nodes=None):
        self.comms_op = comms_op
        self.total_nodes = total_nodes
        self.message_code = msg_code_map[self.comms_op.message_code]
        self.trigger_message = None
        self.sent_count = 0
        self.got_count = 0
        
    def __repr__(self):
        msg = f"{self.__class__.__name__} {self.message_code} {self.comms_op.comms_edge}"
        return msg

    async def is_tripped(self, server):
        done = False
        if self.comms_op.comms_edge in [CommsEdge.before_send,
                                        CommsEdge.after_send,
                                        CommsEdge.after_broadcast]:
            if len(server.out_messages) < 1:
                return done
        if self.comms_op.comms_edge == CommsEdge.before_send:
            message = server.out_messages[0]
            if message.get_code() == self.message_code:
                self.trigger_message = message
                done = True
        elif self.comms_op.comms_edge in [CommsEdge.after_send,
                                          CommsEdge.after_broadcast, ]:
            message = server.out_messages[0]
            if message.get_code() == self.message_code:
                self.trigger_message = message
                if self.comms_op.comms_edge == CommsEdge.after_broadcast:
                    self.sent_count += 1
                    if self.sent_count == self.total_nodes - 1:
                        await self.flush_one_out_message(server, message)
                        done = True
                else:
                    await self.flush_one_out_message(server, message)
                    done = True
        else:
            if len(server.in_messages) < 1:
                return done
            message = server.in_messages[0]
            if message.get_code() == self.message_code:
                self.trigger_message = message
                if self.comms_op.comms_edge == CommsEdge.after_all_responses:
                    # looking to get one from each other node, so count until met
                    self.got_count += 1
                    if self.got_count == self.total_nodes - 1:
                        # make sure it gets handled before pause
                        await server.network.do_next_in_msg(server)
                        done = True
                elif self.comms_op.comms_edge == CommsEdge.after_handle:
                    # make sure it gets handled before pause
                    await server.network.do_next_in_msg(server)
                    done = True
                else:
                    done = True
        return done
    
    async def flush_one_out_message(self, server, message):
        new_list = None
        if not server.block_messages:
            for msg in server.out_messages:
                if new_list is None:
                    new_list = []
                if msg == message:
                    server.logger.debug("FLUSH forwarding message %s", msg)
                    await server.cluster.post_in_message(msg)
                else:
                    new_list.append(msg)
        if new_list is not None:
            server.out_messages = new_list
        return new_list
    
class WhenState(PauseTrigger):

    def __init__(self, log_state):
        self.log_state = log_state
        
    def __repr__(self):
        msg = f"{self.__class__.__name__} {self.log_state}"
        return msg

    async def is_tripped(self, server):
        done = True
        log = server.get_log()
        term = await log.get_term()
        index = await log.get_last_index()
        last_term = await log.get_last_term()
        commit_index = await log.get_commit_index()
        role = server.get_state_code()
        if self.log_state.term != term:
            done = False
        if self.log_state.index != index:
            done = False
        if self.log_state.last_term != last_term:
            done = False
        if self.log_state.commit_index != commit_index:
            done = False
        return done

    
class Sequencer:

    def __init__(self, sequence:Sequence, phase_done_callback=None):
        self.sequence = sequence
        self.phase_done_callback = phase_done_callback
        # copy some values for cleaner code
        self.node_records = {}
        self.cluster = PausingCluster(self.sequence.node_count)
        self.cluster.set_configs()
        for node in self.sequence.start_state.nodes:
            # this will blow up if someone messes up the node it to uri logic
            server = self.cluster.nodes[node.uri]
            self.node_records[node.uri] = NodeRecord(node, server)
        self.nets = None # will be a list of networks if they are split
    
    async def run_sequence(self):
        phase = self.sequence.next_phase()
        while phase:
            await self.run_phase(phase)
            if self.phase_done_callback:
                phase_index = self.sequence.phases.index(phase)
                await self.phase_done_callback(phase, phase_index)
            phase = self.sequence.next_phase()
        
    async def run_phase(self, phase):
        found = []
        awaitables = []
        clears_needed = []
        pending_actions = []
        for node_op in phase.node_ops:
            rec = self.node_records[node_op.node_uri]
            found.append(rec.server)
            if node_op.is_noop:
                continue
            do_now = node_op.get_do_now()
            msg_runner = node_op.get_msg_runner()
            state_runner = node_op.get_state_runner()
            state_validation = node_op.get_state_validate()
            # for now, we accept only one per node_op, in future we might
            # allow combinations, but probably not
            if do_now:
                await self.dispatch_action(do_now.action_code, rec)
            elif msg_runner:
                trigger = WhenMsgOp(msg_runner.comms_op, len(self.node_records))
                rec.server.add_trigger(trigger)
                awaitables.append(rec.server.run_till_triggers())
                clears_needed.append(rec)
                if msg_runner.action_code != ActionCode.pause:
                    pending_actions.append([rec, msg_runner.action_code,])
            elif state_runner:
                trigger = WhenState(state_runner.log_state)
                rec.server.add_trigger(trigger)
                awaitables.append(rec.server.run_till_triggers())
                clears_needed.append(rec)
                if state_runner.action_code != ActionCode.pause:
                    pending_actions.append([rec, state_runner.action_code,])
            elif state_validation:
                self.assert_log_state(rec.server, node_op)
            else:
                raise Exception('invalid node op')
        if len(found) != len(self.node_records):
            phase_index = self.sequence.phases.index(phase)
            raise Exception(f'wrong number of steps for action step {phase_index}')
        if len(awaitables) > 0:
            await asyncio.gather(*awaitables)
        for crec in clears_needed:
            crec.server.clear_triggers()
        for rec,action_code in pending_actions:
            await self.dispatch_action(action_code, rec)

    async def dispatch_action(self, action_code, rec):
        if action_code == ActionCode.network_to_minority:
            await self.split_from_main_net(rec)
        elif action_code == ActionCode.network_to_majority:
            await self.rejoin_main_net(rec)
        elif action_code == ActionCode.crash:
            await self.crash(rec)
        elif action_code == ActionCode.recover:
            await self.recover(rec)
        elif action_code == ActionCode.start_as_replacement:
            await self.new_start(rec)
        elif action_code == ActionCode.start_campaign:
            await self.start_campaign(rec)
        elif action_code == ActionCode.send_heartbeats:
            await self.send_heartbeats(rec)
        elif action_code == ActionCode.noop:
            pass
        elif action_code == ActionCode.pause:
            raise Exception("somehow tried to dispatch a pause action, did you define a do_now action with it?")
        else:
            raise Exception(f'somehow got and invalid action, maybe code out of sync? {action_code}')
        
    async def split_from_main_net(self, rec):
        if self.nets is None:
            self.cluster.split_network()
            self.nets = []
            self.nets.append(self.cluster.net_mgr.get_majority_network())
            self.nets.extend(self.cluster.net_mgr.get_minority_networks())
            min_1 = self.nets[1]
            min_1.add_node(rec.server)
        
    async def rejoin_main_net(self, rec):
        main_net = self.cluster.net_mgr.get_majority_network()
        if rec.server.network != main_net:
            main_net.add_node(rec.server)
            
    async def crash(self, rec):
        await rec.server.simulate_crash()
        
    async def recover(self, rec):
        await rec.server.recover_from_crash()

    async def new_start(self, rec):
        # we need to call crash again to clear the log from the old
        # one, because we assumed the log would be saved when we did the crash
        await rec.server.simulate_crash(save_log=False, save_ops=False)
        await rec.server.recover_from_crash()

    async def start_campaign(self, rec):
        await rec.server.start_campaign()

    async def send_heartbeats(self, rec):
        await rec.server.hull.state.send_heartbeats()
    
    async def assert_log_state(self, server, node_op):
        log = server.get_log()
        term = await log.get_term()
        index = await log.get_last_index()
        last_term = await log.get_last_term()
        commit_index = await log.get_commit_index()
        role = server.get_state_code()
        assert node_op.log_state.term == term
        assert node_op.log_state.index == index
        assert node_op.log_state.last_term == last_term
        assert node_op.log_state.commit_index == commit_index

class StandardElectionSequence(Sequence):

    def __init__(self, node_count):
        super().__init__(node_count=node_count)

    def do_setup(self):

        node_1 = self.nodes_by_id[1]
        phase_1_steps = []
        do_now = DoNow(ActionCode.start_campaign,
                       description="Node 1 starts campaign as though election timeout has occured")
        ps = PhaseStep(node_1.uri, do_now_class=do_now)
        phase_1_steps.append(ps)
        for nid in self.nodes_by_id:
            if nid != 1:
                node = self.nodes_by_id[nid]
                phase_1_steps.append(PhaseStep(node.uri, do_now_class=NoOp()))
        phase_1 = Phase(phase_1_steps, description="Starts campaign at node 1, others do nothing, ensuring node 1 wins election")
        self.add_phase(phase_1)

        phase_2_steps = []
        leader_state = LogState(term=1, index=1, last_term=1, commit_index=1, leader_id=None)
        action_2 = ActionOnState(log_state=leader_state, action_code=ActionCode.pause)
        ps = PhaseStep(node_1.uri, runner_class=action_2)
        phase_2_steps.append(ps)
        comms_op_2b = CommsOp(MessageCode.append_entries_response, CommsEdge.after_send)
        action_2b = ActionOnMessage(comms_op=comms_op_2b, action_code=ActionCode.pause)
        for nid in self.nodes_by_id:
            if nid != 1:
                node = self.nodes_by_id[nid]
                ps = PhaseStep(node.uri, runner_class=action_2b)
                phase_2_steps.append(ps)
        phase_2 = Phase(phase_2_steps,
                        description="Runs until leader sees commit of first log record and all followers have agreed")
        self.add_phase(phase_2)

        phase_3_steps = []
        do_now = DoNow(ActionCode.send_heartbeats, description="Node 1 sends heartbeats to followers")
        ps = PhaseStep(node_1.uri, do_now_class=do_now)
        phase_3_steps.append(ps)
        for nid in self.nodes_by_id:
            if nid != 1:
                node = self.nodes_by_id[nid]
                phase_3_steps.append(PhaseStep(node.uri, do_now_class=NoOp()))
        phase_3 = Phase(phase_3_steps, description="Leader queues heartbeats to followers so they can see commit")
        self.add_phase(phase_3)
        
        phase_4_steps = []
        comms_op_4 = CommsOp(MessageCode.append_entries_response, CommsEdge.after_all_responses)
        action_4 = ActionOnMessage(comms_op=comms_op_4, action_code=ActionCode.pause)
        desc = "Leader runs until it has handled one of the pending append entries response messages"
        ps = PhaseStep(node_1.uri, runner_class=action_4, description=desc)
        phase_4_steps.append(ps)
        follower_state = LogState(term=1, index=1, last_term=1, commit_index=1, leader_id=node_1.uri)
        for nid in self.nodes_by_id:
            if nid != 1:
                node = self.nodes_by_id[nid]
                phase_4_steps.append(PhaseStep(node.uri, validate_class=ValidateState(log_state=follower_state)))
        phase_4 = Phase(phase_4_steps, description="Leader handles all heartbeat responses and followers see commit")
        self.add_phase(phase_4)
