#!/usr/bin/env python
import logging
import json

from dev_tools.cluster_states import (DoNow, NoOp, ValidateState, PhaseStep, ActionOnState, ActionOnMessage, Phase)
from dev_tools.cluster_states import (MessageCode, CommsEdge, ActionCode, LogState, CommsOp, Sequence)
from dev_tools.servers import setup_logging
from dev_tools.stepper import Sequencer, StandardElectionSequence

#extra_logging = [dict(name=__name__, level="debug"),]
#setup_logging(extra_logging)
setup_logging(default_level="debug")
logger = logging.getLogger("test_code")

printing = False
async def test_election_granular_1():
    """ This test builds a sequence of phases that step through the individual parts of the election
    process.
    This test uses the phase sequencer to handle most of the described operations as individual
    phases, plus it checks the log state at various points during the process."""
    
    
    sequence = Sequence(node_count=3,
                        description="Starts 3 node cluster, runs by individaul steps until"\
                        " election is complete and first log message fully committed")

    node_1 = sequence.node_by_id(1)
    node_2 = sequence.node_by_id(2)
    node_3 = sequence.node_by_id(3)

    
    phase_1_steps = []
    do_now = DoNow(ActionCode.start_campaign,
                   description="Node 1 starts campaign as though election timeout has occured")
    ps = PhaseStep(node_1.uri, do_now_class=do_now)
    phase_1_steps.append(ps)
    phase_1_steps.append(PhaseStep(node_2.uri, do_now_class=NoOp()))
    phase_1_steps.append(PhaseStep(node_3.uri, do_now_class=NoOp()))
    phase_1 = Phase(phase_1_steps, description="Starts campaign at node 1, others do nothing, ensuring node 1 wins election")
    sequence.add_phase(phase_1)

    phase_2_steps = []
    comms_op_2 = CommsOp(MessageCode.request_vote, CommsEdge.after_broadcast)
    action_2 = ActionOnMessage(comms_op=comms_op_2, action_code=ActionCode.pause)
    desc = "Node 1 runs until it has broadcast a request vote message to all other nodes"
    ps = PhaseStep(node_1.uri, runner_class=action_2, description=desc)
    phase_2_steps.append(ps)
    comms_op_2b = CommsOp(MessageCode.request_vote_response, CommsEdge.after_send)
    action_2b = ActionOnMessage(comms_op=comms_op_2b, action_code=ActionCode.pause)
    desc = "Follower node runs until it has responded to the request vote message"
    ps = PhaseStep(node_2.uri, runner_class=action_2b, description=desc)
    phase_2_steps.append(ps)
    ps = PhaseStep(node_3.uri, runner_class=action_2b, description=desc)
    phase_2_steps.append(ps)
    phase_2 = Phase(phase_2_steps, description="Runs the request vote cycle until responses have been sent, but not handled")
    sequence.add_phase(phase_2)

    phase_3_steps = []
    comms_op_3 = CommsOp(MessageCode.request_vote_response, CommsEdge.after_handle)
    action_3 = ActionOnMessage(comms_op=comms_op_3, action_code=ActionCode.pause)
    desc = "Leader runs until it has handled one of the pending request vote response messages"
    ps = PhaseStep(node_1.uri, runner_class=action_3, description=desc)
    phase_3_steps.append(ps)
    phase_3_steps.append(PhaseStep(node_2.uri, do_now_class=NoOp()))
    phase_3_steps.append(PhaseStep(node_3.uri, do_now_class=NoOp()))
    phase_3 = Phase(phase_3_steps,
                    description="Node 1 handles the request vote response messages, winning election")
    sequence.add_phase(phase_3)
    
    phase_20_steps = []
    comms_op_20 = CommsOp(MessageCode.append_entries, CommsEdge.after_broadcast)
    action_20 = ActionOnMessage(comms_op=comms_op_20, action_code=ActionCode.pause)
    desc = "Node 1 runs until it has broadcast an append entries message to all other nodes,"
    desc += " which it does after winning election, sending a special noop log message setting the new term in the log"
    ps = PhaseStep(node_1.uri, runner_class=action_20, description=desc)
    phase_20_steps.append(ps)
    comms_op_20b = CommsOp(MessageCode.append_entries_response, CommsEdge.after_send)
    action_20b = ActionOnMessage(comms_op=comms_op_20b, action_code=ActionCode.pause)
    desc = "Follower node runs until it has responded to the first append entries message"
    desc += " after executing the command, which, when processed by leader, will add "
    desc += " to the commit count eventually causing log record commit."
    ps = PhaseStep(node_2.uri, runner_class=action_20b, description=desc)
    phase_20_steps.append(ps)
    ps = PhaseStep(node_3.uri, runner_class=action_20b, description=desc)
    phase_20_steps.append(ps)
    phase_20 = Phase(phase_20_steps, description="Runs all nodes until election is complete and first log update is propogated, but not tallied")
    sequence.add_phase(phase_20)
    
    phase_30_steps = []
    leader_state = LogState(term=1, index=1, last_term=1, commit_index=0, leader_id=None)
    ps = PhaseStep(node_1.uri, validate_class=ValidateState(log_state=leader_state))
    phase_30_steps.append(ps)
    follower_state = LogState(term=1, index=1, last_term=1, commit_index=0, leader_id=node_1.uri)
    ps = PhaseStep(node_2.uri, validate_class=ValidateState(log_state=follower_state))
    phase_30_steps.append(ps)
    ps = PhaseStep(node_3.uri, validate_class=ValidateState(log_state=follower_state))
    phase_30_steps.append(ps)
    phase_30 = Phase(phase_30_steps,
                    description="Validates that all logs contain the first record, but that the commit index is still zero")
    sequence.add_phase(phase_30)


    phase_40_steps = []
    comms_op_40 = CommsOp(MessageCode.append_entries_response, CommsEdge.after_handle)
    action_40 = ActionOnMessage(comms_op=comms_op_40, action_code=ActionCode.pause)
    desc = "Leader runs until it has handled one of the pending append entries response messages"
    ps = PhaseStep(node_1.uri, runner_class=action_40, description=desc)
    phase_40_steps.append(ps)
    phase_40_steps.append(PhaseStep(node_2.uri, do_now_class=NoOp()))
    phase_40_steps.append(PhaseStep(node_3.uri, do_now_class=NoOp()))
    phase_40 = Phase(phase_40_steps,
                    description="Leader handles and tallies append entries response, and commits first log record")
    sequence.add_phase(phase_40)


    phase_50_steps = []
    leader_state = LogState(term=1, index=1, last_term=1, commit_index=1, leader_id=None)
    ps = PhaseStep(node_1.uri, validate_class=ValidateState(log_state=leader_state))
    phase_50_steps.append(ps)
    follower_state = LogState(term=1, index=1, last_term=1, commit_index=0, leader_id=node_1.uri)
    ps = PhaseStep(node_2.uri, validate_class=ValidateState(log_state=follower_state))
    phase_50_steps.append(ps)
    ps = PhaseStep(node_3.uri, validate_class=ValidateState(log_state=follower_state))
    phase_50_steps.append(ps)
    phase_50 = Phase(phase_50_steps,
                    description="Validates that leader committed first log record")
    sequence.add_phase(phase_50)

    phase_60 = Phase(phase_40_steps,
                    description="Leader picks up last pending append entries response, no pessages pending anywhere now")
    sequence.add_phase(phase_60)

    phase_70_steps = []
    do_now = DoNow(ActionCode.send_heartbeats, description="Node 1 sends heartbeats to followers")
    ps = PhaseStep(node_1.uri, do_now_class=do_now)
    phase_70_steps.append(ps)
    phase_70_steps.append(PhaseStep(node_2.uri, do_now_class=NoOp()))
    phase_70_steps.append(PhaseStep(node_3.uri, do_now_class=NoOp()))
    phase_70 = Phase(phase_70_steps, description="Leader queues heartbeats to followers")
    sequence.add_phase(phase_70)

    phase_80_steps = []
    comms_op_80a = CommsOp(MessageCode.append_entries, CommsEdge.after_broadcast)
    action_80a = ActionOnMessage(comms_op=comms_op_80a, action_code=ActionCode.pause)
    ps = PhaseStep(node_1.uri, runner_class=action_80a)
    phase_80_steps.append(ps)
    comms_op_80b = CommsOp(MessageCode.append_entries_response, CommsEdge.after_send)
    action_80b = ActionOnMessage(comms_op=comms_op_80b, action_code=ActionCode.pause)
    ps = PhaseStep(node_2.uri, runner_class=action_80b)
    phase_80_steps.append(ps)
    ps = PhaseStep(node_3.uri, runner_class=action_80b)
    phase_80_steps.append(ps)
    phase_80 = Phase(phase_80_steps, description="Runs all nodes until Leader has sent and followers have processed hearbeats")
    sequence.add_phase(phase_80)

    phase_90_steps = []
    leader_state = LogState(term=1, index=1, last_term=1, commit_index=1, leader_id=None)
    ps = PhaseStep(node_1.uri, validate_class=ValidateState(log_state=leader_state))
    phase_90_steps.append(ps)
    follower_state = LogState(term=1, index=1, last_term=1, commit_index=1, leader_id=node_1.uri)
    ps = PhaseStep(node_2.uri, validate_class=ValidateState(log_state=follower_state))
    phase_90_steps.append(ps)
    ps = PhaseStep(node_3.uri, validate_class=ValidateState(log_state=follower_state))
    phase_90_steps.append(ps)
    phase_90 = Phase(phase_90_steps,
                    description="Validates that everbody shows first record committed")
    sequence.add_phase(phase_90)
    
    phase_100_steps = []
    comms_op_100 = CommsOp(MessageCode.append_entries_response, CommsEdge.after_all_responses)
    action_100 = ActionOnMessage(comms_op=comms_op_100, action_code=ActionCode.pause)
    desc = "Leader runs until it has handled one of the pending append entries response messages"
    ps = PhaseStep(node_1.uri, runner_class=action_100, description=desc)
    phase_100_steps.append(ps)
    phase_100_steps.append(PhaseStep(node_2.uri, do_now_class=NoOp()))
    phase_100_steps.append(PhaseStep(node_3.uri, do_now_class=NoOp()))
    phase_100 = Phase(phase_100_steps, description="Leader handles all heartbeat responses")
    sequence.add_phase(phase_100)

    async def phase_done(phase_result):
        phase = phase_result.phase
        index = phase_result.index
        cluster_state = phase_result.cluster_state
        if printing:
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


    node_1 = sequence.node_by_id(1)
    node_2 = sequence.node_by_id(2)
    node_3 = sequence.node_by_id(3)
    phase_1_steps = []
    do_now = DoNow(ActionCode.start_campaign,
                   description="Node 1 starts campaign as though election timeout has occured")
    ps = PhaseStep(node_1.uri, do_now_class=do_now)
    phase_1_steps.append(ps)
    phase_1_steps.append(PhaseStep(node_2.uri, do_now_class=NoOp()))
    phase_1_steps.append(PhaseStep(node_3.uri, do_now_class=NoOp()))
    phase_1 = Phase(phase_1_steps, description="Starts campaign at node 1, others do nothing, ensuring node 1 wins election")
    sequence.add_phase(phase_1)
    
    phase_2_steps = []
    leader_state = LogState(term=1, index=1, last_term=1, commit_index=1, leader_id=None)
    action_2 = ActionOnState(log_state=leader_state, action_code=ActionCode.pause)
    ps = PhaseStep(node_1.uri, runner_class=action_2)
    phase_2_steps.append(ps)
    comms_op_2b = CommsOp(MessageCode.append_entries_response, CommsEdge.after_send)
    action_2b = ActionOnMessage(comms_op=comms_op_2b, action_code=ActionCode.pause)
    ps = PhaseStep(node_2.uri, runner_class=action_2b)
    phase_2_steps.append(ps)
    ps = PhaseStep(node_3.uri, runner_class=action_2b)
    phase_2_steps.append(ps)
    phase_2 = Phase(phase_2_steps,
                    description="Runs until leader sees commit of first log record and all followers have agreed")
    sequence.add_phase(phase_2)

    phase_3_steps = []
    do_now = DoNow(ActionCode.send_heartbeats, description="Node 1 sends heartbeats to followers")
    ps = PhaseStep(node_1.uri, do_now_class=do_now)
    phase_3_steps.append(ps)
    phase_3_steps.append(PhaseStep(node_2.uri, do_now_class=NoOp()))
    phase_3_steps.append(PhaseStep(node_3.uri, do_now_class=NoOp()))
    phase_3 = Phase(phase_3_steps, description="Leader queues heartbeats to followers so they can see commit")
    sequence.add_phase(phase_3)


    phase_4_steps = []
    comms_op_4 = CommsOp(MessageCode.append_entries_response, CommsEdge.after_all_responses)
    action_4 = ActionOnMessage(comms_op=comms_op_4, action_code=ActionCode.pause)
    desc = "Leader runs until it has handled one of the pending append entries response messages"
    ps = PhaseStep(node_1.uri, runner_class=action_4, description=desc)
    phase_4_steps.append(ps)
    follower_state = LogState(term=1, index=1, last_term=1, commit_index=1, leader_id=node_1.uri)
    phase_4_steps.append(PhaseStep(node_2.uri, validate_class=ValidateState(log_state=follower_state)))
    phase_4_steps.append(PhaseStep(node_3.uri, validate_class=ValidateState(log_state=follower_state)))
    phase_4 = Phase(phase_4_steps, description="Leader handles all heartbeat responses and followers see commit")
    sequence.add_phase(phase_4)
    
    async def phase_done(phase_result):
        phase = phase_result.phase
        index = phase_result.index
        cluster_state = phase_result.cluster_state
        if printing:
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

    sequence = StandardElectionSequence(node_count=3)
    sequence.do_setup()
    
    async def phase_done(phase_result):
        phase = phase_result.phase
        index = phase_result.index
        cluster_state = phase_result.cluster_state
        if printing:
            print(f'\n phase done: {phase.description}\n')
            if len(sequence.phases) > index+1:
                next_phase = sequence.phases[index+1]
                print(f'\n next is: {next_phase.description}\n')
                
    sq = Sequencer(sequence, phase_done)
    await sq.run_sequence()
    await sq.cluster.cleanup()

    # do it again, but with 5 nodes just for giggles
    sequence = StandardElectionSequence(node_count=5)
    sequence.do_setup()
    
    async def phase_done(phase_result):
        phase = phase_result.phase
        index = phase_result.index
        cluster_state = phase_result.cluster_state
        if printing:
            print(f'\n phase done: {phase.description}\n')
            if len(sequence.phases) > index+1:
                next_phase = sequence.phases[index+1]
                print(f'\n next is: {next_phase.description}\n')
        
    sq = Sequencer(sequence, phase_done)
    await sq.run_sequence()
    await sq.cluster.cleanup()
    

async def test_re_election_1():
    sequence = StandardElectionSequence(node_count=3)
    sequence.do_setup()
    
        
    sq = Sequencer(sequence)
    election_results = await sq.run_sequence()

    sequence.clear_phases()
    
    node_1 = sequence.node_by_id(1)
    node_2 = sequence.node_by_id(2)
    node_3 = sequence.node_by_id(3)

    phase_1_steps = []
    crash_now = DoNow(ActionCode.crash, description="Node 1, leader, crashes")
    ps = PhaseStep(node_1.uri, do_now_class=crash_now)
    phase_1_steps.append(ps)
    run_now = DoNow(ActionCode.start_campaign,
                   description="Node 2 starts campaign as though election timeout has occured")
    ps = PhaseStep(node_2.uri, do_now_class=run_now)
    phase_1_steps.append(ps)
    phase_1_steps.append(PhaseStep(node_3.uri, do_now_class=NoOp()))
    phase_1 = Phase(phase_1_steps, description="Leader crashes and node 2 starts election")
    sequence.add_phase(phase_1)

    
    phase_2_steps = []
    phase_2_steps.append(PhaseStep(node_1.uri, do_now_class=NoOp()))
    # only one follower is going to reply, so let's wait for just one
    comms_op_2 = CommsOp(MessageCode.append_entries_response, CommsEdge.after_handle)
    action_2 = ActionOnMessage(comms_op=comms_op_2, action_code=ActionCode.pause)
    ps = PhaseStep(node_2.uri, runner_class=action_2, description="Node 2 runs till wins election")
    phase_2_steps.append(ps)
    comms_op_2b = CommsOp(MessageCode.append_entries_response, CommsEdge.after_send)
    action_2b = ActionOnMessage(comms_op=comms_op_2b, action_code=ActionCode.pause)
    ps = PhaseStep(node_3.uri, runner_class=action_2b)
    phase_2_steps.append(ps)
    phase_2 = Phase(phase_2_steps, description="Node 2 wins election")
    sequence.add_phase(phase_2)

    phase_3_steps = []
    recover_now = DoNow(ActionCode.recover, description="Node 1, old leader, recovers from crash")
    phase_3_steps.append(PhaseStep(node_1.uri, do_now_class=recover_now))
    phase_3_steps.append(PhaseStep(node_2.uri, do_now_class=NoOp()))
    phase_3_steps.append(PhaseStep(node_3.uri, do_now_class=NoOp()))
    phase_3 = Phase(phase_3_steps, description="Node 1 recovers from crash")
    sequence.add_phase(phase_3)
    
    phase_4_steps = []
    do_now = DoNow(ActionCode.send_heartbeats, description="Node 2 sends heartbeats to followers")
    ps = PhaseStep(node_2.uri, do_now_class=do_now)
    phase_4_steps.append(ps)
    phase_4_steps.append(PhaseStep(node_1.uri, do_now_class=NoOp()))
    phase_4_steps.append(PhaseStep(node_3.uri, do_now_class=NoOp()))
    phase_4 = Phase(phase_4_steps, description="Leader queues heartbeats to followers so node 1 can rejoin")
    sequence.add_phase(phase_4)


    phase_5_steps = []
    comms_op_5 = CommsOp(MessageCode.append_entries_response, CommsEdge.after_all_responses)
    action_5 = ActionOnMessage(comms_op=comms_op_5, action_code=ActionCode.pause)
    desc = "Leader runs until it has handled one of the hearbeat response messages"
    ps = PhaseStep(node_2.uri, runner_class=action_5, description=desc)
    phase_5_steps.append(ps)
    comms_op_5b = CommsOp(MessageCode.append_entries_response, CommsEdge.after_send)
    action_5b = ActionOnMessage(comms_op=comms_op_5b, action_code=ActionCode.pause)
    ps = PhaseStep(node_1.uri, runner_class=action_5b)
    phase_5_steps.append(ps)
    ps = PhaseStep(node_3.uri, runner_class=action_5b)
    phase_5_steps.append(ps)
    phase_5 = Phase(phase_5_steps, description="Leader handles all heartbeat responses and node 1 is back in cluster")
    sequence.add_phase(phase_5)
    
    async def phase_done(phase_result):
        phase = phase_result.phase
        index = phase_result.index
        cluster_state = phase_result.cluster_state
        if printing:
            print(f'\n phase done: {phase.description}\n')
            if len(sequence.phases) > index+1:
                next_phase = sequence.phases[index+1]
                print(f'\n next is: {next_phase.description}\n')
            
    sq = Sequencer(sequence, phase_done)
    re_election_results = await sq.run_sequence()
    for phase_result in election_results:
        phase = phase_result.phase
        index = phase_result.index
        cluster_state = phase_result.cluster_state
        print("-"*100)
        print(f"phase index in election={index}, {phase.description}")
        print(json.dumps(cluster_state, default=lambda o:o.__dict__, indent=4))

    for phase_result in re_election_results:
        phase = phase_result.phase
        index = phase_result.index
        cluster_state = phase_result.cluster_state
        print("-"*100)
        print(f"phase index in re-election={index}, {phase.description}")
        print(json.dumps(cluster_state, default=lambda o:o.__dict__, indent=4))

    await sq.cluster.cleanup()

    
async def test_partition_1():
    """ This test runs the standard sequence for starting a cluster and completing the election
    to the point where no more action is pending, all followers have committed the first
    log record and the leader has collected their responses. It then isolates the leader by
    simulating a network partition, such that no messages get from the leader to the followers
    or vise versa. Then it triggers a follower to start an election and waits for it to complete.
    After completion of the election, the simulated network heals and messages can flow again.
    Now there are two nodes that think they are leaders, but the original leader's term is
    lower. Tell that node to send a heartbeat broadcast. It should example the first response
    it sees and resign to become a follower in the new term."""

    sequence = StandardElectionSequence(node_count=3)
    sequence.do_setup()

    printing = True
    target_phase = None
    async def phase_done(phase_result):
        phase = phase_result.phase
        if target_phase == phase:
            breakpoint()
        index = phase_result.index
        cluster_state = phase_result.cluster_state
        if printing:
            print(f'\n phase done: {phase.description}\n')
            print(json.dumps(cluster_state, default=lambda o:o.__dict__, indent=4))
            if len(sequence.phases) > index+1:
                next_phase = sequence.phases[index+1]
                print(f'\n next is: {next_phase.description}\n')
        
    sq = Sequencer(sequence, phase_done)
    election_result = await sq.run_sequence()

    sequence.clear_phases()
    
    node_1 = sequence.node_by_id(1)
    node_2 = sequence.node_by_id(2)
    node_3 = sequence.node_by_id(3)

    phase_0_steps = []
    partition_now = DoNow(ActionCode.network_to_minority, description="Node 1, leader gets partitioned")
    ps = PhaseStep(node_1.uri, do_now_class=partition_now)
    phase_0_steps.append(ps)
    phase_0_steps.append(PhaseStep(node_2.uri, do_now_class=NoOp()))
    phase_0_steps.append(PhaseStep(node_3.uri, do_now_class=NoOp()))
    phase_0 = Phase(phase_0_steps, description="Leader loses network connection")
    sequence.add_phase(phase_0)
    
    phase_1_steps = []
    run_now = DoNow(ActionCode.start_campaign,
                   description="Node 2 starts campaign as though election timeout has occured")
    ps = PhaseStep(node_2.uri, do_now_class=run_now)
    phase_1_steps.append(ps)
    phase_1_steps.append(PhaseStep(node_1.uri, do_now_class=NoOp()))
    phase_1_steps.append(PhaseStep(node_3.uri, do_now_class=NoOp()))
    phase_1 = Phase(phase_1_steps, description="Node 2 starts election")
    sequence.add_phase(phase_1)

    
    phase_2_steps = []
    phase_2_steps.append(PhaseStep(node_1.uri, do_now_class=NoOp()))
    # only one follower is going to reply, so let's wait for just one
    comms_op_2 = CommsOp(MessageCode.append_entries_response, CommsEdge.after_handle)
    action_2 = ActionOnMessage(comms_op=comms_op_2, action_code=ActionCode.pause)
    ps = PhaseStep(node_2.uri, runner_class=action_2, description="Node 2 runs till wins election")
    phase_2_steps.append(ps)
    comms_op_2b = CommsOp(MessageCode.append_entries_response, CommsEdge.after_send)
    action_2b = ActionOnMessage(comms_op=comms_op_2b, action_code=ActionCode.pause)
    ps = PhaseStep(node_3.uri, runner_class=action_2b)
    phase_2_steps.append(ps)
    phase_2 = Phase(phase_2_steps, description="Node 2 wins election")
    sequence.add_phase(phase_2)

    phase_3_steps = []
    recover_now = DoNow(ActionCode.network_to_majority, description="Node 1, old leader, reconnects")
    phase_3_steps.append(PhaseStep(node_1.uri, do_now_class=recover_now))
    phase_3_steps.append(PhaseStep(node_2.uri, do_now_class=NoOp()))
    phase_3_steps.append(PhaseStep(node_3.uri, do_now_class=NoOp()))
    phase_3 = Phase(phase_3_steps, description="Node 1 reconnects")
    sequence.add_phase(phase_3)
    
    phase_4_steps = []
    do_now = DoNow(ActionCode.send_heartbeats, description="Node 1, old leader, sends heartbeats which will be rejected")
    ps = PhaseStep(node_1.uri, do_now_class=do_now)
    phase_4_steps.append(ps)
    phase_4_steps.append(PhaseStep(node_2.uri, do_now_class=NoOp()))
    phase_4_steps.append(PhaseStep(node_2.uri, do_now_class=NoOp()))
    phase_4 = Phase(phase_4_steps, description="Old Leader queues heartbeats to followers")
    sequence.add_phase(phase_4)


    phase_5_steps = []
    comms_op_5 = CommsOp(MessageCode.append_entries_response, CommsEdge.after_all_responses)
    action_5 = ActionOnMessage(comms_op=comms_op_5, action_code=ActionCode.pause)
    desc = "Old Leader runs until it has handled all of the hearbeat response messages"
    ps = PhaseStep(node_1.uri, runner_class=action_5, description=desc)
    phase_5_steps.append(ps)
    comms_op_5b = CommsOp(MessageCode.append_entries_response, CommsEdge.after_send)
    action_5b = ActionOnMessage(comms_op=comms_op_5b, action_code=ActionCode.pause)
    ps = PhaseStep(node_2.uri, runner_class=action_5b)
    phase_5_steps.append(ps)
    ps = PhaseStep(node_3.uri, runner_class=action_5b)
    phase_5_steps.append(ps)
    phase_5 = Phase(phase_5_steps, description="Old leader handles all heartbeat responses, see new term, becomes follower")
    sequence.add_phase(phase_5)

    phase_6_steps = []
    old_leader_state = LogState(term=2, index=1, last_term=1, commit_index=1, leader_id=node_2.uri)
    phase_6_steps.append(PhaseStep(node_1.uri, validate_class=ValidateState(log_state=old_leader_state)))
    phase_6_steps.append(PhaseStep(node_2.uri, do_now_class=NoOp()))
    phase_6_steps.append(PhaseStep(node_3.uri, do_now_class=NoOp()))
    phase_6 = Phase(phase_6_steps, description="Old leader state is not updated yet, except for term and leader_id")
    sequence.add_phase(phase_6)


    phase_7_steps = []
    do_now = DoNow(ActionCode.send_heartbeats, description="Node 2, current leader, sends heartbeats")
    ps = PhaseStep(node_2.uri, do_now_class=do_now)
    phase_7_steps.append(ps)
    phase_7_steps.append(PhaseStep(node_1.uri, do_now_class=NoOp()))
    phase_7_steps.append(PhaseStep(node_3.uri, do_now_class=NoOp()))
    phase_7 = Phase(phase_7_steps, description="New Leader queues heartbeats to followers")
    sequence.add_phase(phase_7)

    phase_8_steps = []
    comms_op_8 = CommsOp(MessageCode.append_entries_response, CommsEdge.after_all_responses)
    action_8 = ActionOnMessage(comms_op=comms_op_8, action_code=ActionCode.pause)
    desc = "Leader runs until it has handled all of the hearbeat response messages"
    ps = PhaseStep(node_2.uri, runner_class=action_8, description=desc)
    phase_8_steps.append(ps)
    comms_op_8b = CommsOp(MessageCode.append_entries_response, CommsEdge.after_send)
    action_8b = ActionOnMessage(comms_op=comms_op_8b, action_code=ActionCode.pause)
    ps = PhaseStep(node_1.uri, runner_class=action_8b)
    phase_8_steps.append(ps)
    ps = PhaseStep(node_3.uri, runner_class=action_8b)
    phase_8_steps.append(ps)
    phase_8 = Phase(phase_8_steps, description="New leader handles all heartbeat responses")
    sequence.add_phase(phase_8)

    re_election_result = await sq.run_sequence()

    await sq.cluster.cleanup()

    
    
