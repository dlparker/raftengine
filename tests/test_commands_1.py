#!/usr/bin/env python
import asyncio
import logging
import pytest
import time
import traceback
from pathlib import Path
from raftengine.messages.request_vote import RequestVoteMessage,RequestVoteResponseMessage
from raftengine.messages.append_entries import AppendEntriesMessage, AppendResponseMessage
from raftengine.api.log_api import LogRec
from dev_tools.memory_log import MemoryLog

from dev_tools.servers import WhenMessageOut, WhenMessageIn
from dev_tools.servers import WhenHasLogIndex
from dev_tools.servers import WhenHasCommitIndex
from dev_tools.servers import WhenInMessageCount, WhenElectionDone
from dev_tools.servers import WhenAllMessagesForwarded, WhenAllInMessagesHandled
from dev_tools.servers import PausingCluster, cluster_maker
from dev_tools.servers import SNormalElection, SNormalCommand, SPartialElection, SPartialCommand
from dev_tools.servers import setup_logging, log_config

#extra_logging = [dict(name="test_code", level="debug"), dict(name="Triggers", level="debug")]
#extra_logging = [dict(name="test_code", level="debug"), ]
#log_config = setup_logging(extra_logging, default_level="debug")
default_level="debug"
#default_level="warn"
log_config = setup_logging(default_level=default_level)
logger = logging.getLogger("test_code")

async def test_command_1(cluster_maker):
    """
    This runs "commands" using highly granular control of test servers 
    so that basic bugs in the first command processing will show up at a detailed 
    level. It also tests that invalid command attempts receive the right response.
    Finally, it validates that crashing a follower, running a command, and recovering
    the follower eventually results in the crashed follower being in sync.
    
    The invalid commands tested are

    1. Sending a command request to a follower, which should result in a redirect
    2. Sending a command request to a candidate, which should result in a "retry", meaning
       that the cluster is currently unable to process commands, so a later retry is recommended

    The second test is performed by doing some artificial manipulation of the state of one of the
    nodes. It is pushed to become a candidate, which will caused it to increase its term. After
    the command is rejected with a retry, the candidate node is forced back to follower mode and
    its term is artificially adjusted down to zero so that it will accept the current leader.

    Because the term is now zero, when the former candidate node receives a heartbeat it
    will accept the current leader.

    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """
    cluster = cluster_maker(3)
    cluster.set_configs()

    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]
    logger = logging.getLogger("test_code")
    cluster.test_trace.start_subtest("Initial election, normal",
                                     test_path_str=str('/'.join(Path(__file__).parts[-2:])),
                                     test_doc_string=test_command_1.__doc__)
    await cluster.start()
    await ts_3.start_campaign()
    sequence = SNormalElection(cluster, 1)
    await cluster.run_sequence(sequence)
    
    assert ts_3.hull.get_state_code() == "LEADER"
    assert ts_1.hull.state.leader_uri == uri_3
    assert ts_2.hull.state.leader_uri == uri_3
    logger.info('------------------------ Election done')
    await cluster.start_auto_comms()

    cluster.test_trace.start_subtest("Run one command, normal sequence till leader commit")
    command_result = await ts_3.run_command("add 1")
    assert command_result.result is not None
    assert command_result.error is None
    assert ts_3.operations.total == 1
    # now we need to trigger a heartbeat so that
    # followers will see the commitIndex is higher
    # and apply and locally commit
    await cluster.stop_auto_comms()
    cluster.test_trace.start_subtest("Finish command by notifying followers of commit with heartbeat")
    await ts_3.hull.state.send_heartbeats()
    logger.info('------------------------ Leader has command completion, heartbeats going out')
    term = await ts_3.hull.log.get_term()
    index = await ts_3.hull.log.get_last_index()
    assert index == 2 # one for start term, one for command
    ts_1.set_trigger(WhenMessageOut(AppendResponseMessage.get_code()))
    ts_2.set_trigger(WhenMessageOut(AppendResponseMessage.get_code()))
    ts_3.set_trigger(WhenMessageIn(AppendResponseMessage.get_code()))
    await asyncio.gather(ts_1.run_till_triggers(),
                         ts_2.run_till_triggers(),
                         ts_3.run_till_triggers())
    ts_1.clear_triggers()
    ts_2.clear_triggers()
    ts_3.clear_triggers()
    assert ts_1.operations.total == 1
    assert ts_2.operations.total == 1
    assert await ts_1.hull.log.get_term() == term
    assert await ts_1.hull.log.get_last_index() == index
    assert await ts_2.hull.log.get_term() == term
    assert await ts_2.hull.log.get_last_index() == index
    logger.debug('------------------------ Correct command done')

    await cluster.stop_auto_comms()
    cluster.test_trace.start_subtest("Trying to run command at follower, looking for redirect")
    command_result = await ts_1.run_command("add 1")
    assert command_result.redirect == uri_3
    logger.debug('------------------------ Correct redirect (follower) done')
    
    cluster.test_trace.start_subtest("Pushing one follower to candidate, then trying command to it, looking for retry")
    orig_term =  await ts_1.hull.get_term() 
    await ts_1.do_leader_lost()
    assert ts_1.hull.get_state_code() == "CANDIDATE"
    command_result = await ts_1.run_command("add 1")
    assert command_result.retry is not None
    logger.debug('------------------------ Correct retry (candidate) done')
    # get the leader to send it a heartbeat while it is a candidate
    cluster.test_trace.start_subtest("Pushing Leader to send heartbeats, after forcing candidate's term back down")
    # cleanup traces of attempt to start election
    logger.debug('------------------------ forcing candidate term down')
    ts_1.clear_all_msgs()
    await ts_1.log.set_term(orig_term)
    logger.debug('------------------------ sending heartbeats, should make candidate resign')
    await ts_3.hull.state.send_heartbeats()
    await cluster.deliver_all_pending()
    assert ts_1.hull.get_state_code() == "FOLLOWER"
    assert ts_1.hull.state.leader_uri == uri_3


    # Now simulate a crash of a follower,
    # and then do a couple of commands. Once the
    # commands are committed, let heartbeats go out
    # so the tardy follower will catch up

    cluster.test_trace.start_subtest("Crashing one follower, then running command to ensure it works with only one follower")
    await ts_1.simulate_crash()
    logger.debug('------------------------ Running command ---')
    sequence = SPartialCommand(cluster, "add 1", voters=[uri_2, uri_3])
    command_result = await cluster.run_sequence(sequence)
    assert ts_3.operations.total == 2
    sequence = SPartialCommand(cluster, "add 1", voters=[uri_2, uri_3])
    command_result = await cluster.run_sequence(sequence)
    assert ts_3.operations.total == 3
    start_time = time.time()
    while time.time() - start_time < 0.1 and ts_2.operations.total != 3:
        await asyncio.sleep(0.0001)
    assert ts_2.operations.total == 3
    await cluster.deliver_all_pending()
    await ts_3.hull.state.send_heartbeats()
    await cluster.deliver_all_pending()
    cluster.test_trace.start_subtest("Recovering follower, then pushing hearbeat to get it to catch up")
    logger.debug('------------------------ Unblocking, doing hearbeats, should catch up ---')
    await ts_1.recover_from_crash()
    await ts_3.hull.state.send_heartbeats()
    await cluster.start_auto_comms()
    start_time = time.time()
    while time.time() - start_time < 0.1 and ts_1.operations.total != 3:
        await asyncio.sleep(0.0001)
    assert ts_1.operations.total == 3
    await cluster.stop_auto_comms()
    await cluster.deliver_all_pending()
    await cluster.deliver_all_pending()
    logger.debug('------------------------ Tardy follower caught up ---')
    cluster.test_trace.end_subtest()
    cluster.test_trace.to_condensed_org()

async def test_command_sqlite_1(cluster_maker):
    """
    Test election and state machine command operations while using
    a SQLite implementation of the Logo's. Most other tests use
    an in memory log implementation, so this test is mostly focused
    on whether the basic logging operations work correctly against
    a real db. If another test is using SQLite and has problems,
    this test might help call out something basic.

    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """
    from dev_tools.sqlite_log import SqliteLog
    cluster = cluster_maker(3, use_log=SqliteLog)
    cluster.set_configs()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]
    logger = logging.getLogger("test_code")
    cluster.test_trace.start_subtest("Initial election, normal",
                                     test_path_str=str('/'.join(Path(__file__).parts[-2:])),
                                     test_doc_string=test_command_sqlite_1.__doc__)
    await cluster.start()
    await ts_3.start_campaign()

    await cluster.run_election()
    assert ts_3.hull.get_state_code() == "LEADER"
    assert ts_1.hull.state.leader_uri == uri_3
    assert ts_2.hull.state.leader_uri == uri_3
    logger.info('------------------------ Election done')
    await cluster.start_auto_comms()

    cluster.test_trace.start_subtest("Run command and check results at all nodes")
    command_result = await cluster.run_command("add 1", 1)
    
    assert ts_1.operations.total == 1
    assert ts_2.operations.total == 1
    assert ts_3.operations.total == 1
    term = await ts_3.hull.log.get_term()
    index = await ts_3.hull.log.get_last_index()
    assert index == 2 # first index will be the start term record
    assert await ts_1.hull.log.get_term() == term
    assert await ts_1.hull.log.get_last_index() == index
    assert await ts_2.hull.log.get_term() == term
    assert await ts_2.hull.log.get_last_index() == index
    logger.debug('------------------------ Correct command done')
    rec_1 = await ts_1.hull.log.read(index)
    rec_2 = await ts_2.hull.log.read(index)
    rec_3 = await ts_3.hull.log.read(index)
    assert rec_1.result == rec_2.result 
    assert rec_1.result == rec_3.result
    new_rec = LogRec.from_dict(rec_1.__dict__)
    assert new_rec.result == rec_1.result
    await cluster.stop_auto_comms()
    
async def double_leader_inner(cluster, discard):
    """
    This function is called once by each of two actual test functions. Once with
    the "discard" flag False and once with it True.

    test_command_2_leaders_1 runs with discard = True

    test_command_2_leaders_2  runs with discard = False

    The sequence begins with a normal election, followed by a state machine command
    which all of the nodes replicate.

    Next there is a network problem and a new election is started. When the discard
    flag is True this looks like a regular partition type test, the new leader will
    take over and allow a new command. The rejoin of the old leader will proceed
    as normal.

    However, when the discard flag is False, the messages sent to and from the original
    leader will not be lost, they will be delivered when it rejoins. Although this
    sort of transient network problem is not common, it certainly can happen, and
    it is possible that a follower's leader lost timeout fires while leader
    heartbeats are delayed but not lost.

    For example, it is possible that the first leader sent heartbeats
    to the cluster that did not get delivered because of network, and
    just when the cluster gave up and called an election the leader
    host machine also had a massive slow down (maybe trying to switch
    networks but thrashing on low memory) such the the leader code
    could not execute for a second or so but the message delivery was
    never really blocked.  These are the sort of timing and network
    problem that Raft is meant to handle. They might be unlikely, but
    they are possible.

    Regardless of how the affected messages are handled, the rejoin should deliver the same
    result, the new leader's state being replicated to the old leader.

    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.

    """
    
    cluster.set_configs()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]
    logger = logging.getLogger("test_code")
    
    cluster.test_trace.start_subtest("Initial election, normal",
                                     test_path_str=str('/'.join(Path(__file__).parts[-2:])),
                                     test_doc_string=double_leader_inner.__doc__)
    await cluster.start()
    await ts_1.start_campaign()
    await cluster.run_election()
    
    assert ts_1.hull.get_state_code() == "LEADER"
    assert ts_2.hull.state.leader_uri == uri_1
    assert ts_3.hull.state.leader_uri == uri_1
    logger.info('------------------------ Election done')
    logger.info('---------!!!!!!! starting comms')
    cluster.test_trace.start_subtest("Running command normally")
    command_result = await cluster.run_command("add 1", 1)
    assert ts_2.operations.total == 1
    assert ts_3.operations.total == 1
    logger.debug('------------------------ Correct command done')


    logger.info('---------!!!!!!! stopping comms')
    await cluster.stop_auto_comms()
    cluster.test_trace.start_subtest("Simlating network/speed problems for leader and starting election at node 2 ")
    ts_1.block_network()
    logger.info('------------------ isolated leader, starting new election')
    await ts_2.start_campaign()
    await cluster.run_election()
    assert ts_1.hull.get_state_code() == "LEADER"
    assert ts_2.hull.get_state_code() == "LEADER"
    assert ts_3.hull.state.leader_uri == uri_2

    command_result = await cluster.run_command("add 1", 1)
    assert ts_2.operations.total == 2
    assert ts_3.operations.total == 2


    if discard:
        # Will discard the messages that were blocked 
        # so it looks like the network was broken
        # during that time.
        cluster.test_trace.start_subtest("Letting old leader rejoin network, but losing any messages sent during problem period")
        ts_1.unblock_network()
        logger.info('---------!!!!!!! starting comms')
        await cluster.start_auto_comms()
    else:
        # Will deliver messages that were blocked during
        # the disconnect period, simulating some sort
        # of major latency issue, or maybe just a timing
        # problem. For example, it is possible that the
        # first leader sent heartbeats to the cluster
        # that did not get delivered, and just when the
        # cluster gave up and called an election the
        # leader host machine also had a massive slow down such
        # the the leader code could not execute for a second or
        # so but the message delivery was never really blocked.
        # These are the sort of timing and network problem
        # that Raft is meant to handle. They might be unlikely,
        # but they are possible.
        logger.info('------------------ unblocking and delivering ')
        cluster.test_trace.start_subtest("Letting old leader rejoin network and delivering all lost messages")

        ts_1.unblock_network(deliver=True)
        await cluster.deliver_all_pending()

    logger.debug('------------------ Command AppendEntries should get rejected -')

    
    cluster.test_trace.start_subtest("New leader sending heartbeats")
    logger.info('\n\n sending heartbeat, but old leader should already be up to date\n\n')
    await ts_2.hull.state.send_heartbeats()
    await cluster.deliver_all_pending()
    assert ts_1.operations.total == ts_2.operations.total
    await cluster.stop_auto_comms()
    
async def test_command_2_leaders_1(cluster_maker):
    cluster = cluster_maker(3)
    await double_leader_inner(cluster, True)    

async def test_command_2_leaders_2(cluster_maker):
    cluster = cluster_maker(3)
    await double_leader_inner(cluster, False)    


async def test_command_2_leaders_3(cluster_maker):
    """

    This test ensures that trying to run a command at a node that
    was a leader and got partitioned off long enough to miss a new
    election and then returned to connection will return a redirect
    to the new leader.

    The sequence begins with a normal election, followed by a state machine command
    which all of the nodes replicate.

    Next there is a network problem for the leader and a new election is started. 

    Once the election is complete the old leader rejoins the majority network
    but before any other message pass to update it, it gets sent a command request.
    The results should be a rediect to the new leader.

    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """
    
    cluster = cluster_maker(3)
    cluster.set_configs()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]
    logger = logging.getLogger("test_code")
    
    cluster.test_trace.start_subtest("Initial election, normal",
                                     test_path_str=str('/'.join(Path(__file__).parts[-2:])),
                                     test_doc_string=test_command_2_leaders_3.__doc__)
    await cluster.start()
    await ts_1.start_campaign()
    await cluster.run_election()
    
    assert ts_1.hull.get_state_code() == "LEADER"
    assert ts_2.hull.state.leader_uri == uri_1
    assert ts_3.hull.state.leader_uri == uri_1
    logger.info('------------------------ Election done')
    logger.info('---------!!!!!!! starting comms')
    cluster.test_trace.start_subtest("Running command normally")
    command_result = await cluster.run_command("add 1", 1)
    assert ts_2.operations.total == 1
    assert ts_3.operations.total == 1
    logger.debug('------------------------ Correct command done')

    # Now we want to block all messages from the leader, then
    # trigger a follower to hold an election, wait for it to
    # win, then unblock the old leader, and then try another
    # command. The leader should figure out it doesn't lead
    # anymore and give back a redirect

    logger.info('---------!!!!!!! stopping comms')
    await cluster.stop_auto_comms()
    cluster.test_trace.start_subtest("Simlating network/speed problems for leader and starting election at node 2 ")
    ts_1.block_network()
    logger.info('------------------ isolated leader, starting new election')
    await ts_2.start_campaign()
    await cluster.run_election()
    await cluster.deliver_all_pending()
    assert ts_1.hull.get_state_code() == "LEADER"
    assert ts_2.hull.get_state_code() == "LEADER"
    assert ts_3.hull.state.leader_uri == uri_2

    cluster.test_trace.start_subtest("Trying to run command at leader that is no longer connected")
    
    # can't use cluster command runner here, it will connect to the actual leader
    command_result = None
    async def command_runner(ts):
        nonlocal command_result
        logger.debug('running command in background')
        try:
            command_result = await ts.run_command("add 1", timeout=0.01)
            logger.debug('running command in background done with NO error')
        except Exception as e:
            logger.debug('running command in background error %s', traceback.format_exc())
            command_result = e
            logger.debug('running command in background done with error')
    logger.debug('------------------------ Running command ---')
    ts_1.unblock_network()
    await cluster.start_auto_comms()
    asyncio.create_task(command_runner(ts_1))
    start_time = time.time()
    while time.time() - start_time < 0.25 and command_result is None:
        await asyncio.sleep(0.01)
    assert command_result is not None
    assert command_result.redirect == uri_2
    
async def test_command_after_heal_1(cluster_maker):
    """
    The goal for this test is for a candidate to receive an append entries message from a leader of a lower term.
    This can happen when a network partition resolves before a new election has completed and the 
    old leader sends a heartbeat out. There wouldn't be any problem with the candidate resigning in this
    case because everybody's log states match, but Raft is conservative on this point and requires
    that the candidate reject an append entries of a lower term.

    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """


    cluster = cluster_maker(3)
    cluster.set_configs()

    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]
    logger = logging.getLogger("test_code")

    cluster.test_trace.start_subtest("Initial election, normal",
                                     test_path_str=str('/'.join(Path(__file__).parts[-2:])),
                                     test_doc_string=test_command_after_heal_1.__doc__)
    await cluster.start()
    await ts_1.start_campaign()
    await cluster.run_election()
    
    assert ts_1.hull.get_state_code() == "LEADER"
    assert ts_2.hull.state.leader_uri == uri_1
    assert ts_3.hull.state.leader_uri == uri_1
    logger.info('-------------- Election done, about to split network leaving leader %s isolated ', uri_1)
    cluster.test_trace.start_subtest("Node 1 is leader, splitting network to isolate it")
    part1 = {uri_1: ts_1}
    part2 = {uri_2: ts_2,
             uri_3: ts_3}
    await cluster.split_network([part1, part2])
    #logger.info('-------------- Split network done, starting election of %s', uri_2)
    # now ts_2 and ts_3 are alone, have ts_2
    cluster.test_trace.start_subtest("Triggering node 2 to start an election, then healing network and triggering old leader to send heartbeats")
    await ts_2.start_campaign()
    assert ts_2.hull.get_state_code() == "CANDIDATE"
    last_term = await ts_2.hull.log.get_term()
    await cluster.unsplit()
    assert ts_1.hull.get_state_code() == "LEADER"
    logger.info('-------------- telling reconnected old leader %s to send heartbeats, %s should reject in candidate',
                uri_1, uri_2)
    assert ts_1.hull.get_state_code() == "LEADER"
    await ts_1.hull.state.send_heartbeats()
    logger.info('-------------- old leader %s sent heartbeats', uri_1)
    await cluster.deliver_all_pending()

    # don't know how the election will turn out for sure, probably ts_2 will win
    # important thing is that ts_1 responded properly to higher term in response,
    # meaning that candidate reply did its thing
    assert await ts_1.hull.log.get_term() == last_term
    
async def test_follower_explodes_in_command(cluster_maker):
    """
    This tests that operations are correct in the case where the state machine operation at a single
    follower experiences an error during command execution, one that does not crash the node.

    The items that are tested are that
    1. The command succeeds because the leader and one follower agree
    2. That the follower will retry the command next time it gets a heartbeat 
    

    There is no discussion in the Raft paper about the possibility that the state machine command
    processing could experience an error that does not crash the node, but also does not
    allow the command to be processed. I guess they were thinking about compliled languages
    that are more likely to crash the process on some serious bug than to detect the bug and try
    to continue, but this is python which might well have such behavior. I guess it might not
    then be technically a "state machine", but anything more complex than storing a value (like
    etcd) is likely to have the possibilty of this kind of failure.

    Rather than try to develop some general mechanism for dealing with this, I throw up my
    hands and just promise to let you know if it fails at the leader. If that happens then
    the log record is not committed, so your job is to figure out how to clear the problem condition
    and retry.

    If it happens at a single follower then that may be okay, if there was more than a quorum, since enough
    other nodes applied it successfully that the cluster can move on even if the follower continues to
    fail to apply. There is not yet a mechanism for reporting the error at a follower, but when there is
    will be local to the follower, and some external action will need to be taken to allow that follower
    to finish the commit and move on. If the follower was part of a minimum quorum, your whole cluster
    will be blocked until you fix it.

    This test fixed the simulated problem so that the first retry succeeds.
    
    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """

    cluster = cluster_maker(3)
    cluster.set_configs()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]
    logger = logging.getLogger("test_code")

    cluster.test_trace.start_subtest("Initial election, normal",
                                     test_path_str=str('/'.join(Path(__file__).parts[-2:])),
                                     test_doc_string=test_follower_explodes_in_command.__doc__)
    await cluster.start()
    await ts_1.start_campaign()

    await cluster.run_election()
    assert ts_1.hull.get_state_code() == "LEADER"
    assert ts_1.hull.state.leader_uri == uri_1
    assert ts_2.hull.state.leader_uri == uri_1
    logger.info('------------------------ Election done')

    command_result = await cluster.run_command("add 1", 1)
    assert ts_1.operations.total == 1
    assert ts_2.operations.total == 1
    assert ts_3.operations.total == 1
    logger.debug('------------------------ Correct command done')
    cluster.test_trace.start_subtest("Node 1 is leader, one command completed and all nodes in sync, rigging node 3 to explode processing next command")

    # The node 3 follower will blow up trying to apply command, so
    # we use the test control sequence that allows us to specify
    # which nodes need to make it all the way to committing the
    # command.
    ts_3.operations.explode = True
    sequence = SPartialCommand(cluster, "add 1", voters=[uri_1, uri_2])
    command_result = await cluster.run_sequence(sequence)
    await cluster.deliver_all_pending()

    # make sure the command worked, at the leader and node 2
    assert command_result.result == 2
    assert ts_1.operations.total == 2
    assert ts_2.operations.total == 2
    assert ts_3.operations.total == 1

    cluster.test_trace.start_subtest("Second command succeed, but not at node3. Disarming bomb and sending hearbeats, should cause run and commit")
    # clear the trigger and run heartbeats, node 3 should rerun command and succeed
    ts_3.operations.explode = False
    await ts_1.hull.state.send_heartbeats()
    await cluster.deliver_all_pending()
    assert ts_3.operations.total == 2


async def test_leader_explodes_in_command(cluster_maker):
    """
    This tests that operations are correct in the case where the state machine operation at 
    the leader experiences an error during command execution, one that does not crash the node.

    There is no discussion in the Raft paper about the possibility that the state machine command
    processing could experience an error that does not crash the node, but also does not
    allow the command to be processed. 

    Rather than try to develop some general mechanism for dealing with this, I throw up my
    hands and just promise to let you know if it fails at the leader. If that happens then
    the log record is not committed, so your job is to figure out how to clear the problem condition
    and retry.

    This test clears the error condition so that sending heartbeats should trigger a successful retry.

    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """
    cluster = cluster_maker(3)
    cluster.set_configs()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]
    logger = logging.getLogger("test_code")

    cluster.test_trace.start_subtest("Initial election, normal, running one command in normal fashion after election",
                                     test_path_str=str('/'.join(Path(__file__).parts[-2:])),
                                     test_doc_string=test_leader_explodes_in_command.__doc__)
    await cluster.start()
    await ts_1.start_campaign()

    await cluster.run_election()
    assert ts_1.hull.get_state_code() == "LEADER"
    assert ts_1.hull.state.leader_uri == uri_1
    assert ts_2.hull.state.leader_uri == uri_1
    logger.info('------------------------ Election done')

    command_result = await cluster.run_command("add 1", 1)
    
    assert ts_1.operations.total == 1
    assert ts_2.operations.total == 1
    assert ts_3.operations.total == 1
    logger.debug('------------------------ Correct command done')

    cluster.test_trace.start_subtest("Node 1 is leader, rigging it to explode on command and runnning command")

    # now arrange for leader to blow up.
    ts_1.operations.explode = True
    command_result = await cluster.run_command("add 1", timeout=0.01)
    assert command_result is not None
    assert command_result.error is not None
    
    cluster.test_trace.start_subtest("Leader node 1 returned an error from command request, clearing trigger and sending heartbeats to retry")
    ts_1.operations.explode = False
    await ts_1.send_heartbeats()
    await cluster.deliver_all_pending()
    start_time = time.time()
    while time.time() - start_time < 0.1 and ts_1.operations.total < 2:
        await asyncio.sleep(0.0001)
    assert ts_1.operations.total == 2
    cluster.test_trace.start_subtest("Leader node 1 retry succeeded, now need another heartbeat to trigger followers to apply and commit")
    await ts_1.send_heartbeats()
    await cluster.deliver_all_pending()
    assert ts_2.operations.total == 2
    assert ts_3.operations.total == 2
    await cluster.stop_auto_comms()
    
async def test_long_catchup(cluster_maker):
    """
    Test that a follower catches up properly after a network partition and then a heal and rejoin.
    Do a normal election, then a command. Then partition the network to isolate node 3 and run a
    bunch of commands. Then heal the network and broadcast a heartbeat which will cause node 3
    and the leader to dialog until node 3 is caught up.
    
    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """

    
    cluster = cluster_maker(3)
    cluster.set_configs()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]
    logger = logging.getLogger("test_code")

    cluster.test_trace.start_subtest("Initial election, normal, run one command, normal",
                                     test_path_str=str('/'.join(Path(__file__).parts[-2:])),
                                     test_doc_string=test_long_catchup.__doc__)
    await cluster.start()
    await ts_1.start_campaign()
    await cluster.run_election()
    
    assert ts_1.hull.get_state_code() == "LEADER"
    assert ts_2.hull.state.leader_uri == uri_1
    assert ts_3.hull.state.leader_uri == uri_1
    logger.info('------------------------ Election done')
    logger.info('---------!!!!!!! starting comms')

    command_result = await cluster.run_command("add 1", 1)
    assert ts_2.operations.total == 1
    assert ts_3.operations.total == 1
    logger.debug('------------------------ Correct command done')


    # Make sure that the number of commands we send
    # now will require a couple of catchup messages, so
    # use the leader's runtime value 
    loop_limit = ts_1.hull.state.max_entries_per_message * 2 + 2
    cluster.test_trace.start_subtest(f"Node 1 is leader, partitioning network so that node 3 is isolated, then running {loop_limit} commands")
    
    part1 = {uri_3: ts_3}
    part2 = {uri_1: ts_1,
             uri_2: ts_2}
    logger.info('---------!!!!!!! spliting network ')
    await cluster.split_network([part1, part2])
    logger.info('------------------ follower %s isolated, starting command loop', uri_3)
    await cluster.stop_auto_comms()


    # Watching debug level logging for a bunch of commands is painful,
    # so lets temporarily reduce the log messages to only those from the state classes
    # and put it back when we are done
    global log_config
    old_levels = dict()

    trim_loggers = True
    if trim_loggers:
        for logger_name, spec in log_config['loggers'].items():
            logger = logging.getLogger(logger_name)
            if  logger_name == "test_commands_1" or logger_name == "Leader" or logger_name == "Follower":
                continue
            old_levels[logger_name] = logger.level
            logger.setLevel('ERROR')

    for i in range(loop_limit):
        command_result = await cluster.run_command("add 1", 1)
    total = ts_1.operations.total
    assert ts_2.operations.total == total
    assert ts_3.operations.total != total
    # restore the loggers
    if trim_loggers:
        for logger_name in old_levels:
            logger = logging.getLogger(logger_name)
            old_value = old_levels[logger_name]
            logger.setLevel(old_value)
    # will discard the messages that were blocked
    logger.debug('------------------ unblocking follower %s should catch up to total %d', uri_3, total)
    cluster.test_trace.start_subtest("Commands run, now healing network and triggering a heartbeat, node 3 should catch up")
    #await cluster.deliver_all_pending()
    await cluster.unsplit()
    logger.info('---------!!!!!!! starting comms')
    #await cluster.start_auto_comms()
    await ts_1.hull.state.send_heartbeats()

    start_time = time.time()
    while time.time() - start_time < 0.2 and ts_3.operations.total < total:
        await cluster.deliver_all_pending()
    assert ts_3.operations.total == total
    await cluster.stop_auto_comms()
    logger.info('------------------------ All caught up')

async def test_full_catchup(cluster_maker):
    """
    This tests that a follower that crashes and restarts with an empty log will catchup all the
    way to the latest cluster commited state.
    
    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """
    cluster = cluster_maker(3)
    cluster.set_configs()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]
    logger = logging.getLogger("test_code")

    cluster.test_trace.start_subtest("Initial election, normal",
                                     test_path_str=str('/'.join(Path(__file__).parts[-2:])),
                                     test_doc_string=test_full_catchup.__doc__)
    await cluster.start()
    await ts_1.start_campaign()
    await cluster.run_election()
    
    assert ts_1.hull.get_state_code() == "LEADER"
    assert ts_2.hull.state.leader_uri == uri_1
    assert ts_3.hull.state.leader_uri == uri_1
    logger.info('------------------------ Election done')

    # Now we simulate the crash of  one follower,
    # then run a bunch of commands, restart the
    # follower and make sure that
    # the catchup process gets them all the messages

    cluster.test_trace.start_subtest("Node 1 is leader, crashing node 3, then running two commands")
    logger.info('---------!!!!!!! stopping comms')
    await ts_3.simulate_crash()
    logger.info('------------------ follower %s crashed, starting command loop', uri_3)
    command_result = await cluster.run_command("add 1", 1)
    assert ts_1.operations.total == 1
    assert ts_2.operations.total == ts_1.operations.total
    logger.debug('------------------------ Correct command 1 done')
    command_result = await cluster.run_command("add 1", 1)
    assert ts_1.operations.total == 2
    assert ts_2.operations.total == ts_1.operations.total
    logger.debug('------------------------ Correct command 2 done')


    cluster.test_trace.start_subtest("Recovering node 3, then sending heartbeat which should result in catchup")
    await ts_3.recover_from_crash(save_log=False, save_ops=False)
    logger.info('------------------ restarting follower %s should catch up to total %d', uri_3, ts_1.operations.total)
    assert ts_3.operations.total != ts_1.operations.total
    logger.info('---------!!!!!!! starting comms')
    await ts_1.hull.state.send_heartbeats()
    start_time = time.time()
    while time.time() - start_time < 0.5 and ts_3.operations.total < ts_1.operations.total:
        await cluster.deliver_all_pending()
    assert ts_3.operations.total == ts_1.operations.total
    logger.info('------------------------ All caught up')

async def test_follower_run_error(cluster_maker):
    """
    This test part of an incomplete error reporting mechanism that allows state machine commands to catch
    errors and return an indication that an error happened when executed in a follower. The follower code
    will consider the error to invalidate the state transition and so the record will not be committed.
    The unfinished part is how the fact of the error gets back to the library user's code.
    
    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """
    
    cluster = cluster_maker(3)
    cluster.set_configs()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]
    logger = logging.getLogger("test_code")

    cluster.test_trace.start_subtest("Initial election, normal",
                                     test_path_str=str('/'.join(Path(__file__).parts[-2:])),
                                     test_doc_string=test_follower_run_error.__doc__)
    await cluster.start()
    await ts_1.start_campaign()
    await cluster.run_election()
    assert ts_1.hull.get_state_code() == "LEADER"
    assert ts_2.hull.state.leader_uri == uri_1
    assert ts_3.hull.state.leader_uri == uri_1
    logger.info('------------------------ Election done')

    # Simulate crash of one follower, run a comand,
    # then restart it and send heartbeats, causing
    # it to try to catch up. However have the
    # "state machine" command pretend it had
    # an error. This should excersize some
    # error handling code, but then the next command
    # should go through without problem.

    logger.info('---------!!!!!!! spliting network ')
    cluster.test_trace.start_subtest("Node 1 is leader, crashing node 3  and running a command")
    await ts_3.simulate_crash()
    logger.info('------------------ follower %s crashed, running', uri_3)
    
    command_result = await cluster.run_command("add 1", 1)
    assert ts_1.operations.total == 1
    assert ts_2.operations.total == ts_1.operations.total
    logger.debug('------------------------ Correct command 1 done')

    logger.info('------------------ restarted follower %s to hit error running command', uri_3)
    cluster.test_trace.start_subtest("Setting return error trigger on node 3, recovering it, and running heartbeats")
    ts_3.operations.return_error = True
    await ts_3.recover_from_crash()
    logger.info('---------!!!!!!! starting comms')
    await ts_1.hull.state.send_heartbeats()
    start_time = time.time()
    while time.time() - start_time < 0.5 and not ts_3.operations.reported_error:
        await cluster.deliver_all_pending()
    assert ts_3.operations.reported_error
    logger.info('------------------------ Error as expected, removing error insertion and trying again')
    cluster.test_trace.start_subtest("Node 3 reported error, removing trigger and running heartbeats to retry")
    ts_3.operations.return_error = False
    await ts_1.hull.state.send_heartbeats()
    start_time = time.time()
    while time.time() - start_time < 0.5 and ts_3.operations.total !=ts_1.operations.total:
        await cluster.deliver_all_pending()
    assert ts_3.operations.total == ts_1.operations.total


async def test_follower_rewrite_1(cluster_maker):

    """
    Tests scenarios where a server becomes leader, then gets disconnected from followers, but not
    yet realizing that it accepts some client command requests, logs them, sends  broadcast to
    try to commit them.

    The while this is going on, the followers hold an election and a new leader is chosen. That
    leader accepts some commands and is able to commit them because it has a quorum, 2 servers,
    in this case, itself and one follower.

    Then the old leader connects to the new leader, and messages  fly to the effect that the
    ex-leader has log records that  match the index of the new leader, but not their term, so those
    records have to be discarded. After that is done the ex-leader  can now catchup, with the help of
    messages from the new leader.

    Sheesh.
    
    cluster.test_trace.start_subtest("Node 1 is leader, sending heartbeat so replies will tell us that followers did commit")
    """
    cluster = cluster_maker(3)
    cluster.set_configs()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]
    logger = logging.getLogger("test_code")

    cluster.test_trace.start_subtest("Initial election, normal",
                                     test_path_str=str('/'.join(Path(__file__).parts[-2:])),
                                     test_doc_string=test_follower_rewrite_1.__doc__)
    await cluster.start()
    await ts_1.start_campaign()
    await cluster.run_election()
    assert ts_1.hull.get_state_code() == "LEADER"
    assert ts_2.hull.state.leader_uri == uri_1
    assert ts_3.hull.state.leader_uri == uri_1
    logger.info('------------------------ Election done')
    await cluster.start_auto_comms()
    running_total = 0
    last_index = await ts_1.log.get_last_index()

    cluster.test_trace.start_subtest("Node 1 is leader, blocking network traffic to it like a partition and sending two commands")
    logger.info("---------!!!!!!! Blocking leader's network ")
    ts_1.block_network()
    logger.info('---------!!!!!!! Sending blocked leader two "sub 1" commands')
    command_result = await ts_1.run_command("sub 1", timeout=0.01)
    assert command_result.timeout_expired
    command_result = await ts_1.run_command("sub 1", timeout=0.01)
    assert command_result.timeout_expired
    assert await ts_1.hull.log.get_last_index() == last_index + 2
    logger.debug('------------------------ Starting an election, favoring %s ---', uri_2)
    # now let the others do a new election
    cluster.test_trace.start_subtest("Starting election at node 2, which it will win")
    await ts_2.start_campaign()
    await cluster.run_election()
    assert ts_2.hull.get_state_code() == "LEADER"
    logger.debug('------------------------ Elected %s, demoting ex-leader %s ---', uri_2, uri_1)
    cluster.test_trace.start_subtest("Demoting old leader to follower but not reconnecting it yet, running one command at new leader")
    # we do this now so that the cluster run_command method will not get confused
    # about which server is the leader
    await ts_1.do_demote_and_handle(None)
    assert ts_1.hull.get_state_code() == "FOLLOWER"

    # now do a command at the new leader
    command_result = None
    logger.debug('------------------------ Running commands at new leader---')
    command_result = await cluster.run_command("add 1", timeout=0.01)
    running_total += 1
    assert command_result.result == running_total
    
    total = ts_2.operations.total
    assert ts_3.operations.total == total

    # Now let the ex-leader rejoin, already demoted to follower, and let it get a heartbeat. this should trigger it to
    # overwrite the existing records in its log with the new ones from the new leader.
    #
    # The old leader will have three records in its log.
    # The first record will be the "no-op" or "TERM_START" record for when the ex-leader took power.
    # Then there will be two command records for the two "sub 1" commands. These will
    # be index 2 and 3 with term 1.
    #
    # The new leader's log will have three records in its log, the TERM_START for term 1, which will match the
    # record in the old leader's log at index 1 term 1. Then it will have a TERM_START for term 2.
    # Then it will have the command record at index 2 term 2.
    #
    # When the heartbeat arrives at the old leader, it should negotiate with the new leader and learn
    # that it needs to delete the records with the wrong term.
    #
    # After that it should accept the new command record as catchup, and be up to date
    #

    first_relevant_index = 2
    orig_rec_2 = await ts_1.hull.log.read(first_relevant_index) # the first record is start term record
    orig_rec_3 = await ts_1.hull.log.read(first_relevant_index + 1)
    logger.debug('------------------------ Unblocking ex-leader, should overwrite logs ---')
    cluster.test_trace.start_subtest("Reconnecting old leader as follower, now it should have log records that have to be purged, sending heartbeats")
    ts_1.unblock_network() # discards missed messages
    await ts_2.hull.state.send_heartbeats()
    await cluster.deliver_all_pending()
    start_time = time.time()
    # log should be 1 for start_term, and one for each command, so 4
    while time.time() - start_time < 0.5 and await ts_1.log.get_last_index() != await ts_2.log.get_last_index():
        await cluster.deliver_all_pending()
    t1_last_i = await ts_1.log.get_last_index()
    t2_last_i = await ts_2.log.get_last_index()
    assert t1_last_i ==  t2_last_i
    new_rec_2 = await ts_1.log.read(first_relevant_index) # the first record is start term recordc
    new_rec_3 = await ts_1.log.read(first_relevant_index + 1)
    assert new_rec_3.command != orig_rec_2.command
    assert new_rec_3.command != orig_rec_3.command
    assert ts_1.operations.total == ts_2.operations.total


