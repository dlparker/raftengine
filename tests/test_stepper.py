#!/usr/bin/env python
import asyncio
import logging
import pytest
import time

from dev_tools.cluster_states import (MessageCode, CommsEdge, ActionCode, RoleCode,
                                      RunState, NetworkMode, LogState, CommsOp, PhaseStep, ActionPhase,
                                      ActionOnMessage, NodeState, ClusterState,  Sequence, Phase)
from dev_tools.cluster_states import (DoNow, NoOp, ValidateState, PhaseStep2, ActionOnState, ActionOnMessage)
from dev_tools.stepper import Sequencer, StandardElectionSequence
from dev_tools.servers import setup_logging


#extra_logging = [dict(name=__name__, level="debug"),]
#setup_logging(extra_logging)
setup_logging(default_level="debug")
logger = logging.getLogger("test_code")


async def test_election_steps_1():
    """ This test builds a sequence of phases that step through the later parts of the election
    process, after the 3 nodes in the cluster have elected a leader and the leader begins the
    term. The leader commits an empty log record marking the beginning of the term, and it
    then broadcasts an append entries message announcing that. The followers apply and reply,
    and the leader commits. In normal operations the leader would eventually send a heartbeat
    or a new log record and this would update the followers as to the commit index. However,
    in this testing mode the heartbeat timer is effectively disabled so the test code has
    to prod the leader into sending a heartbeat broadcast. That causes the followers to update
    their commit index and reply. Once the leader has processed the replies, the cluster is
    quiet with no further operations needed until an new log record is created.

    This test uses the phase sequencer to handle most of the described operations as individual
    phases, plus it checks the log state at various points during the process."""
    
    
    sequence = Sequence(node_count=3,
                        description="Starts 3 node cluster, runs by individaul steps until"\
                        " election is complete and first log message fully committed")


    node_1 = sequence.nodes_by_id[1]
    node_2 = sequence.nodes_by_id[2]
    node_3 = sequence.nodes_by_id[3]
    phase_1_steps = []
    do_now = DoNow(ActionCode.start_campaign,
                   description="Node 1 starts campaign as though election timeout has occured")
    ps = PhaseStep2(node_1.uri, do_now_class=do_now)
    phase_1_steps.append(ps)
    phase_1_steps.append(PhaseStep2(node_2.uri, do_now_class=NoOp()))
    phase_1_steps.append(PhaseStep2(node_3.uri, do_now_class=NoOp()))
    phase_1 = Phase(phase_1_steps, description="Starts campaign at node 1, others do nothing, ensuring node 1 wins election")
    sequence.add_phase(phase_1)
    
    phase_2_steps = []
    comms_op_1 = CommsOp(MessageCode.append_entries, CommsEdge.after_broadcast)
    action_1 = ActionOnMessage(comms_op=comms_op_1, action_code=ActionCode.pause)
    desc = "Node 1 runs until it has broadcast an append entries message to all other nodes,"
    desc += " which it does after winning election, sending a special noop log message setting the new term in the log"
    ps = PhaseStep2(node_1.uri, runner_class=action_1, description=desc)
    phase_2_steps.append(ps)
    
    comms_op_2 = CommsOp(MessageCode.append_entries_response, CommsEdge.after_send)
    action_2 = ActionOnMessage(comms_op=comms_op_2, action_code=ActionCode.pause)
    desc = "Follower node runs until it has responded to the first append entries message"
    desc += " after executing the command, which, when processed by leader, will add "
    desc += " to the commit count eventually causing log record commit."
    ps = PhaseStep2(node_2.uri, runner_class=action_2, description=desc)
    phase_2_steps.append(ps)
    ps = PhaseStep2(node_3.uri, runner_class=action_2, description=desc)
    phase_2_steps.append(ps)
    phase_2 = Phase(phase_2_steps, description="Runs all nodes until election is complete and first log update is propogated, but not tallied")
    sequence.add_phase(phase_2)

    
    phase_3_steps = []
    leader_state = LogState(term=1, index=1, last_term=1, commit_index=0, leader_id=None)
    ps = PhaseStep2(node_1.uri, validate_class=ValidateState(log_state=leader_state))
    phase_3_steps.append(ps)
    follower_state = LogState(term=1, index=1, last_term=1, commit_index=0, leader_id=node_1.uri)
    ps = PhaseStep2(node_2.uri, validate_class=ValidateState(log_state=follower_state))
    phase_3_steps.append(ps)
    ps = PhaseStep2(node_3.uri, validate_class=ValidateState(log_state=follower_state))
    phase_3_steps.append(ps)
    phase_3 = Phase(phase_3_steps,
                    description="Validates that all logs contain the first record, but that the commit index is still zero")
    sequence.add_phase(phase_3)


    phase_4_steps = []
    comms_op_3 = CommsOp(MessageCode.append_entries_response, CommsEdge.after_handle)
    action_3 = ActionOnMessage(comms_op=comms_op_3, action_code=ActionCode.pause)
    desc = "Leader runs until it has handled one of the pending append entries response messages"
    ps = PhaseStep2(node_1.uri, runner_class=action_3, description=desc)
    phase_4_steps.append(ps)
    phase_4_steps.append(PhaseStep2(node_2.uri, do_now_class=NoOp()))
    phase_4_steps.append(PhaseStep2(node_3.uri, do_now_class=NoOp()))
    phase_4 = Phase(phase_4_steps,
                    description="Leader handles and tallies append entries response, and commits first log record")
    sequence.add_phase(phase_4)


    phase_5_steps = []
    leader_state = LogState(term=1, index=1, last_term=1, commit_index=1, leader_id=None)
    ps = PhaseStep2(node_1.uri, validate_class=ValidateState(log_state=leader_state))
    phase_5_steps.append(ps)
    follower_state = LogState(term=1, index=1, last_term=1, commit_index=0, leader_id=node_1.uri)
    ps = PhaseStep2(node_2.uri, validate_class=ValidateState(log_state=follower_state))
    phase_5_steps.append(ps)
    ps = PhaseStep2(node_3.uri, validate_class=ValidateState(log_state=follower_state))
    phase_5_steps.append(ps)
    phase_5 = Phase(phase_5_steps,
                    description="Validates that leader committed first log record")
    sequence.add_phase(phase_5)

    phase_6 = Phase(phase_4_steps,
                    description="Leader picks up last pending append entries response, no pessages pending anywhere now")
    sequence.add_phase(phase_6)


    phase_7_steps = []
    do_now = DoNow(ActionCode.send_heartbeats, description="Node 1 sends heartbeats to followers")
    ps = PhaseStep2(node_1.uri, do_now_class=do_now)
    phase_7_steps.append(ps)
    phase_7_steps.append(PhaseStep2(node_2.uri, do_now_class=NoOp()))
    phase_7_steps.append(PhaseStep2(node_3.uri, do_now_class=NoOp()))
    phase_7 = Phase(phase_7_steps, description="Leader queues heartbeats to followers")
    sequence.add_phase(phase_7)

    phase_8_steps = []
    comms_op_8a = CommsOp(MessageCode.append_entries, CommsEdge.after_broadcast)
    action_8a = ActionOnMessage(comms_op=comms_op_8a, action_code=ActionCode.pause)
    ps = PhaseStep2(node_1.uri, runner_class=action_8a)
    phase_8_steps.append(ps)
    comms_op_8b = CommsOp(MessageCode.append_entries_response, CommsEdge.after_send)
    action_8b = ActionOnMessage(comms_op=comms_op_8b, action_code=ActionCode.pause)
    ps = PhaseStep2(node_2.uri, runner_class=action_8b)
    phase_8_steps.append(ps)
    ps = PhaseStep2(node_3.uri, runner_class=action_8b)
    phase_8_steps.append(ps)
    phase_8 = Phase(phase_8_steps, description="Runs all nodes until Leader has sent and followers have processed hearbeats")
    sequence.add_phase(phase_8)

    phase_9_steps = []
    leader_state = LogState(term=1, index=1, last_term=1, commit_index=1, leader_id=None)
    ps = PhaseStep2(node_1.uri, validate_class=ValidateState(log_state=leader_state))
    phase_9_steps.append(ps)
    follower_state = LogState(term=1, index=1, last_term=1, commit_index=1, leader_id=node_1.uri)
    ps = PhaseStep2(node_2.uri, validate_class=ValidateState(log_state=follower_state))
    phase_9_steps.append(ps)
    ps = PhaseStep2(node_3.uri, validate_class=ValidateState(log_state=follower_state))
    phase_9_steps.append(ps)
    phase_9 = Phase(phase_9_steps,
                    description="Validates that everbody shows first record committed")
    sequence.add_phase(phase_9)
    
    phase_10_steps = []
    comms_op_10 = CommsOp(MessageCode.append_entries_response, CommsEdge.after_all_responses)
    action_10 = ActionOnMessage(comms_op=comms_op_10, action_code=ActionCode.pause)
    desc = "Leader runs until it has handled one of the pending append entries response messages"
    ps = PhaseStep2(node_1.uri, runner_class=action_10, description=desc)
    phase_10_steps.append(ps)
    phase_10_steps.append(PhaseStep2(node_2.uri, do_now_class=NoOp()))
    phase_10_steps.append(PhaseStep2(node_3.uri, do_now_class=NoOp()))
    phase_10 = Phase(phase_10_steps, description="Leader handles all heartbeat responses")
    sequence.add_phase(phase_10)

    async def phase_done(phase, index):
        print(f'\n phase done: {phase.description}\n')
        if len(sequence.phases) > index+1:
            next_phase = sequence.phases[index+1]
            print(f'\n next is: {next_phase.description}\n')
            
        
    sq = Sequencer(sequence, phase_done)
    await sq.run_sequence()
    await sq.cluster.stop_auto_comms()
    await sq.cluster.cleanup()
    

async def test_election_short_1():
    """ This test builds a sequence of phases that step through the later parts of the election
    process, after the 3 nodes in the cluster have elected a leader and the leader begins the
    term. The leader commits an empty log record marking the beginning of the term, and it
    then broadcasts an append entries message announcing that. The followers apply and reply,
    and the leader commits. In normal operations the leader would eventually send a heartbeat
    or a new log record and this would update the followers as to the commit index. However,
    in this testing mode the heartbeat timer is effectively disabled so the test code has
    to prod the leader into sending a heartbeat broadcast. That causes the followers to update
    their commit index and reply. Once the leader has processed the replies, the cluster is
    quiet with no further operations needed until an new log record is created.

    This test uses the phase sequencer to handle the absolute minimum number of operations
    possible in this test environment in order to have a fully consistent cluster."""
    
    sequence = Sequence(node_count=3,
                        description="Starts 3 node cluster, runs with minimal steps "\
                        " until election is complete and first log message fully committed")


    node_1 = sequence.nodes_by_id[1]
    node_2 = sequence.nodes_by_id[2]
    node_3 = sequence.nodes_by_id[3]
    phase_1_steps = []
    do_now = DoNow(ActionCode.start_campaign,
                   description="Node 1 starts campaign as though election timeout has occured")
    ps = PhaseStep2(node_1.uri, do_now_class=do_now)
    phase_1_steps.append(ps)
    phase_1_steps.append(PhaseStep2(node_2.uri, do_now_class=NoOp()))
    phase_1_steps.append(PhaseStep2(node_3.uri, do_now_class=NoOp()))
    phase_1 = Phase(phase_1_steps, description="Starts campaign at node 1, others do nothing, ensuring node 1 wins election")
    sequence.add_phase(phase_1)
    
    phase_2_steps = []
    leader_state = LogState(term=1, index=1, last_term=1, commit_index=1, leader_id=None)
    action_2 = ActionOnState(log_state=leader_state, action_code=ActionCode.pause)
    ps = PhaseStep2(node_1.uri, runner_class=action_2)
    phase_2_steps.append(ps)
    comms_op_2b = CommsOp(MessageCode.append_entries_response, CommsEdge.after_send)
    action_2b = ActionOnMessage(comms_op=comms_op_2b, action_code=ActionCode.pause)
    ps = PhaseStep2(node_2.uri, runner_class=action_2b)
    phase_2_steps.append(ps)
    ps = PhaseStep2(node_3.uri, runner_class=action_2b)
    phase_2_steps.append(ps)
    phase_2 = Phase(phase_2_steps,
                    description="Runs until leader sees commit of first log record and all followers have agreed")
    sequence.add_phase(phase_2)

    phase_3_steps = []
    do_now = DoNow(ActionCode.send_heartbeats, description="Node 1 sends heartbeats to followers")
    ps = PhaseStep2(node_1.uri, do_now_class=do_now)
    phase_3_steps.append(ps)
    phase_3_steps.append(PhaseStep2(node_2.uri, do_now_class=NoOp()))
    phase_3_steps.append(PhaseStep2(node_3.uri, do_now_class=NoOp()))
    phase_3 = Phase(phase_3_steps, description="Leader queues heartbeats to followers so they can see commit")
    sequence.add_phase(phase_3)


    phase_4_steps = []
    comms_op_4 = CommsOp(MessageCode.append_entries_response, CommsEdge.after_all_responses)
    action_4 = ActionOnMessage(comms_op=comms_op_4, action_code=ActionCode.pause)
    desc = "Leader runs until it has handled one of the pending append entries response messages"
    ps = PhaseStep2(node_1.uri, runner_class=action_4, description=desc)
    phase_4_steps.append(ps)
    follower_state = LogState(term=1, index=1, last_term=1, commit_index=1, leader_id=node_1.uri)
    phase_4_steps.append(PhaseStep2(node_2.uri, validate_class=ValidateState(log_state=follower_state)))
    phase_4_steps.append(PhaseStep2(node_3.uri, validate_class=ValidateState(log_state=follower_state)))
    phase_4 = Phase(phase_4_steps, description="Leader handles all heartbeat responses and followers see commit")
    sequence.add_phase(phase_4)
    
    async def phase_done(phase, index):
        print(f'\n phase done: {phase.description}\n')
        if len(sequence.phases) > index+1:
            next_phase = sequence.phases[index+1]
            print(f'\n next is: {next_phase.description}\n')
            
        
    sq = Sequencer(sequence, phase_done)
    await sq.run_sequence()
    await sq.cluster.stop_auto_comms()
    await sq.cluster.cleanup()
    
async def test_stnd_election_1():
    """ This test runs the standard sequence for starting a cluster and completing the election
    to the point where no more action is pending, all followers have committed the first
    log record and the leader has collected their responses. This puts the cluster in
    a ready state for doing other testing."""

    start_sequence = StandardElectionSequence(node_count=3)
    start_sequence.do_setup()
    
    async def phase_done(phase, index):
        print(f'\n phase done: {phase.description}\n')
        if len(start_sequence.phases) > index+1:
            next_phase = start_sequence.phases[index+1]
            print(f'\n next is: {next_phase.description}\n')
        
    sq = Sequencer(start_sequence, phase_done)
    await sq.run_sequence()
    await sq.cluster.cleanup()

    # do it again, but with 5 nodes just for giggles
    start_sequence = StandardElectionSequence(node_count=5)
    start_sequence.do_setup()
    
    async def phase_done(phase, index):
        print(f'\n phase done: {phase.description}\n')
        if len(start_sequence.phases) > index+1:
            next_phase = start_sequence.phases[index+1]
            print(f'\n next is: {next_phase.description}\n')
        
    sq = Sequencer(start_sequence, phase_done)
    await sq.run_sequence()
    await sq.cluster.cleanup()
    

async def test_re_election_1():
    sequence = StandardElectionSequence(node_count=3)
    sequence.do_setup()
    
        
    sq = Sequencer(sequence)
    await sq.run_sequence()

    sequence.clear_phases()
    
    node_1 = sequence.nodes_by_id[1]
    node_2 = sequence.nodes_by_id[2]
    node_3 = sequence.nodes_by_id[3]

    phase_1_steps = []
    crash_now = DoNow(ActionCode.crash, description="Node 1, leader, crashes")
    ps = PhaseStep2(node_1.uri, do_now_class=crash_now)
    phase_1_steps.append(ps)
    run_now = DoNow(ActionCode.start_campaign,
                   description="Node 1 starts campaign as though election timeout has occured")
    ps = PhaseStep2(node_2.uri, do_now_class=run_now)
    phase_1_steps.append(ps)
    phase_1_steps.append(PhaseStep2(node_3.uri, do_now_class=NoOp()))
    phase_1 = Phase(phase_1_steps, description="Leader crashes and node 2 starts election")
    sequence.add_phase(phase_1)

    
    phase_2_steps = []
    phase_2_steps.append(PhaseStep2(node_1.uri, do_now_class=NoOp()))
    # only one follower is going to reply, so let's wait for just one
    comms_op_2 = CommsOp(MessageCode.append_entries_response, CommsEdge.after_handle)
    action_2 = ActionOnMessage(comms_op=comms_op_2, action_code=ActionCode.pause)
    ps = PhaseStep2(node_2.uri, runner_class=action_2, description="Node 2 runs till wins election")
    phase_2_steps.append(ps)
    comms_op_2b = CommsOp(MessageCode.append_entries_response, CommsEdge.after_send)
    action_2b = ActionOnMessage(comms_op=comms_op_2b, action_code=ActionCode.pause)
    ps = PhaseStep2(node_3.uri, runner_class=action_2b)
    phase_2_steps.append(ps)
    phase_2 = Phase(phase_2_steps, description="Node 2 wins election")
    sequence.add_phase(phase_2)

    phase_3_steps = []
    recover_now = DoNow(ActionCode.recover, description="Node 1, old leader, recovers from crash")
    phase_3_steps.append(PhaseStep2(node_1.uri, do_now_class=recover_now))
    phase_3_steps.append(PhaseStep2(node_2.uri, do_now_class=NoOp()))
    phase_3_steps.append(PhaseStep2(node_3.uri, do_now_class=NoOp()))
    phase_3 = Phase(phase_3_steps, description="Node 1 recovers from crash")
    sequence.add_phase(phase_3)
    
    phase_4_steps = []
    do_now = DoNow(ActionCode.send_heartbeats, description="Node 2 sends heartbeats to followers")
    ps = PhaseStep2(node_2.uri, do_now_class=do_now)
    phase_4_steps.append(ps)
    phase_4_steps.append(PhaseStep2(node_1.uri, do_now_class=NoOp()))
    phase_4_steps.append(PhaseStep2(node_3.uri, do_now_class=NoOp()))
    phase_4 = Phase(phase_4_steps, description="Leader queues heartbeats to followers so node 1 can rejoin")
    sequence.add_phase(phase_4)


    phase_5_steps = []
    comms_op_5 = CommsOp(MessageCode.append_entries_response, CommsEdge.after_all_responses)
    action_5 = ActionOnMessage(comms_op=comms_op_5, action_code=ActionCode.pause)
    desc = "Leader runs until it has handled one of the hearbeat response messages"
    ps = PhaseStep2(node_2.uri, runner_class=action_5, description=desc)
    phase_5_steps.append(ps)
    comms_op_5b = CommsOp(MessageCode.append_entries_response, CommsEdge.after_send)
    action_5b = ActionOnMessage(comms_op=comms_op_5b, action_code=ActionCode.pause)
    ps = PhaseStep2(node_1.uri, runner_class=action_5b)
    phase_5_steps.append(ps)
    ps = PhaseStep2(node_3.uri, runner_class=action_5b)
    phase_5_steps.append(ps)
    phase_5 = Phase(phase_5_steps, description="Leader handles all heartbeat responses and node 1 is back in cluster")
    sequence.add_phase(phase_5)
    
    async def phase_done(phase, index):
        print(f'\n phase done: {phase.description}\n')
        if len(sequence.phases) > index+1:
            next_phase = sequence.phases[index+1]
            print(f'\n next is: {next_phase.description}\n')
            
    sq = Sequencer(sequence, phase_done)
    await sq.run_sequence()
    
    await sq.cluster.cleanup()

    
