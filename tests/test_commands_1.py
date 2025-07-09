#!/usr/bin/env python
import asyncio
import logging
import time
import traceback
import os
from raftengine.messages.append_entries import AppendResponseMessage
from raftengine.api.log_api import LogRec
from dev_tools.features import registry

from dev_tools.triggers import WhenMessageOut, WhenMessageIn
from dev_tools.pausing_cluster import cluster_maker
from dev_tools.sequences import SNormalElection, SPartialCommand
from dev_tools.features import FeatureRegistry
from raftengine.deck.log_control import TemporaryLogControl
from dev_tools.log_control import setup_logging

log_control = setup_logging()
logger = logging.getLogger("test_code")

registry = FeatureRegistry.get_registry()

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
    await cluster.test_trace.define_test("Testing basic command processing with detailed control", logger=logger)
    f_normal_election = registry.get_raft_feature("leader_election", "all_yes_votes.with_pre_vote")
    spec = dict(used=[f_normal_election], tested=[])
    await cluster.test_trace.start_test_prep("Normal election", features=spec)
    await cluster.start()
    await ts_3.start_campaign()
    sequence = SNormalElection(cluster, 1)
    await cluster.run_sequence(sequence)
    
    assert ts_3.get_role_name() == "LEADER"
    assert ts_1.get_leader_uri() == uri_3
    assert ts_2.get_leader_uri() == uri_3
    logger.info('------------------------ Election done')
    await cluster.start_auto_comms()

    f_state_machine_cmd = registry.get_raft_feature("state_machine_command", "all_in_sync")
    f_log_replication = registry.get_raft_feature("log_replication", "normal_replication")
    spec = dict(used=[f_state_machine_cmd, f_log_replication], tested=[])
    await cluster.test_trace.start_subtest("Run one command, normal sequence till leader commit", features=spec)
    command_result = await ts_3.run_command("add 1")
    assert command_result.result is not None
    assert command_result.error is None
    assert ts_3.operations.total == 1
    # now we need to trigger a heartbeat so that
    # followers will see the commitIndex is higher
    # and apply and locally commit
    await cluster.stop_auto_comms()
    f_heartbeat = registry.get_raft_feature("log_replication", "heartbeat_only")
    spec = dict(used=[f_heartbeat], tested=[])
    await cluster.test_trace.start_subtest("Finish command by notifying followers of commit with heartbeat", features=spec)
    await ts_3.send_heartbeats()
    logger.info('------------------------ Leader has command completion, heartbeats going out')
    term = await ts_3.log.get_term()
    index = await ts_3.log.get_last_index()
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
    assert await ts_1.log.get_term() == term
    assert await ts_1.log.get_last_index() == index
    assert await ts_2.log.get_term() == term
    assert await ts_2.log.get_last_index() == index
    logger.debug('------------------------ Correct command done')

    await cluster.stop_auto_comms()
    f_request_redirect = registry.get_raft_feature("state_machine_command", "request_redirect")
    spec = dict(used=[], tested=[f_request_redirect])
    await cluster.test_trace.start_subtest("Trying to run command at follower, looking for redirect", features=spec)
    command_result = await ts_1.run_command("add 1")
    assert command_result.redirect == uri_3
    logger.debug('------------------------ Correct redirect (follower) done')
    
    f_retry_during_election = registry.get_raft_feature("state_machine_command", "retry_during_election")
    spec = dict(used=[], tested=[f_retry_during_election])
    await cluster.test_trace.start_subtest("Pushing one follower to candidate, then trying command to it, looking for retry", features=spec)
    orig_term =  await ts_1.get_term() 
    await ts_1.do_leader_lost()
    assert ts_1.get_role_name() == "CANDIDATE"
    command_result = await ts_1.run_command("add 1")
    assert command_result.retry is not None
    logger.debug('------------------------ Correct retry (candidate) done')
    # get the leader to send it a heartbeat while it is a candidate
    await cluster.test_trace.start_subtest("Pushing Leader to send heartbeats, after forcing candidate's term back down")
    # cleanup traces of attempt to start election
    logger.debug('------------------------ forcing candidate term down')
    ts_1.clear_all_msgs()
    await ts_1.log.set_term(orig_term)
    logger.debug('------------------------ sending heartbeats, should make candidate resign')
    await ts_3.send_heartbeats()
    await cluster.deliver_all_pending()
    assert ts_1.get_role_name() == "FOLLOWER"
    assert ts_1.get_leader_uri() == uri_3


    # Now simulate a crash of a follower,
    # and then do a couple of commands. Once the
    # commands are committed, let heartbeats go out
    # so the tardy follower will catch up

    f_minimal_node_count = registry.get_raft_feature("state_machine_command", "minimal_node_count")
    spec = dict(used=[], tested=[f_minimal_node_count])
    await cluster.test_trace.start_subtest("Crashing one follower, then running command to ensure it works with only one follower", features=spec)
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
    await ts_3.send_heartbeats()
    await cluster.deliver_all_pending()
    f_follower_recovery = registry.get_raft_feature("log_replication", "follower_recovery_catchup")
    spec = dict(used=[], tested=[f_follower_recovery])
    await cluster.test_trace.start_subtest("Recovering follower, then pushing hearbeat to get it to catch up", features=spec)
    logger.debug('------------------------ Unblocking, doing hearbeats, should catch up ---')
    await ts_1.recover_from_crash()
    await ts_3.send_heartbeats()
    await cluster.start_auto_comms()
    start_time = time.time()
    while time.time() - start_time < 0.1 and ts_1.operations.total != 3:
        await asyncio.sleep(0.0001)
    assert ts_1.operations.total == 3
    await cluster.stop_auto_comms()
    await cluster.deliver_all_pending()
    await cluster.deliver_all_pending()
    logger.debug('------------------------ Tardy follower caught up ---')
    await cluster.test_trace.end_subtest()

async def test_command_sqlite_1(cluster_maker):
    """
    Test election and state machine command operations while using
    a SQLite implementation of the log storage. Most other tests use
    an in-memory log implementation, so this test validates that the
    basic Raft operations work correctly with persistent database storage.

    This test covers:
    - Leader election with pre-vote (using SQLite for vote persistence)
    - State machine command processing with database log storage
    - Log replication and commit notification with persistent storage
    - Validation that all Raft safety properties hold with SQLite backend

    The test ensures SQLite compatibility for core Raft operations including
    log entry persistence, term tracking, and vote recording. If other tests
    using SQLite encounter issues, this test helps isolate basic storage problems.

    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """
    from dev_tools.sqlite_log import SqliteLog
    cluster = cluster_maker(3, use_log=SqliteLog)
    cluster.set_configs()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]
    logger = logging.getLogger("test_code")
    await cluster.test_trace.define_test("Testing command operations with SQLite log", logger=logger)
    f_normal_election = registry.get_raft_feature("leader_election", "all_yes_votes.with_pre_vote")
    spec = dict(used=[f_normal_election], tested=[])
    await cluster.test_trace.start_test_prep("Normal election", features=spec)
    await cluster.start()
    await ts_3.start_campaign()

    await cluster.run_election()
    assert ts_3.get_role_name() == "LEADER"
    assert ts_1.get_leader_uri() == uri_3
    assert ts_2.get_leader_uri() == uri_3
    logger.info('------------------------ Election done')
    await cluster.start_auto_comms()

    f_sqlite_compat = registry.get_raft_feature("log_storage", "sqlite_compatibility")
    f_state_machine_cmd = registry.get_raft_feature("state_machine_command", "all_in_sync")
    f_log_replication = registry.get_raft_feature("log_replication", "normal_replication")
    f_heartbeat = registry.get_raft_feature("log_replication", "heartbeat_only")
    spec = dict(used=[f_log_replication, f_heartbeat], tested=[f_sqlite_compat, f_state_machine_cmd])
    await cluster.test_trace.start_subtest("Run command and check results at all nodes", features=spec)
    command_result = await cluster.run_command("add 1", 1)
    
    assert ts_1.operations.total == 1
    assert ts_2.operations.total == 1
    assert ts_3.operations.total == 1
    term = await ts_3.log.get_term()
    index = await ts_3.log.get_last_index()
    assert index == 2 # first index will be the start term record
    assert await ts_1.log.get_term() == term
    assert await ts_1.log.get_last_index() == index
    assert await ts_2.log.get_term() == term
    assert await ts_2.log.get_last_index() == index
    logger.debug('------------------------ Correct command done')
    rec_1 = await ts_1.log.read(index)
    rec_2 = await ts_2.log.read(index)
    rec_3 = await ts_3.log.read(index)
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

    #ts_1.operations.dump_state = True
    #ts_2.operations.dump_state = True
    #ts_3.operations.dump_state = True
    await cluster.test_trace.define_test("Testing command processing with dual leaders", logger=logger)
    
    # Section 1: Normal election to establish initial leader
    f_normal_election = registry.get_raft_feature("leader_election", "all_yes_votes.with_pre_vote")
    spec = dict(used=[f_normal_election], tested=[])
    await cluster.test_trace.start_test_prep("Normal election", features=spec)
    await cluster.start()
    await ts_1.start_campaign()
    await cluster.run_election()
    
    assert ts_1.get_role_name() == "LEADER"
    assert ts_2.get_leader_uri() == uri_1
    assert ts_3.get_leader_uri() == uri_1
    logger.info('------------------------ Election done')
    
    # Section 2: Normal command processing
    f_normal_command = registry.get_raft_feature("state_machine_command", "all_in_sync")
    spec = dict(used=[f_normal_command], tested=[])
    logger.info('---------!!!!!!! starting comms')
    await cluster.test_trace.start_subtest("Running command normally", features=spec)
    command_result = await cluster.run_command("add 1", 1)
    assert ts_2.operations.total == 1
    assert ts_3.operations.total == 1
    logger.debug('------------------------ Correct command done')

    logger.info('---------!!!!!!! stopping auto comms')
    await cluster.stop_auto_comms()
    
    # Section 3: Network partition and new election
    f_leader_isolation = registry.get_raft_feature("network_partition", "leader_isolation")
    f_partition_election = registry.get_raft_feature("leader_election", "partition_recovery")
    spec = dict(used=[f_leader_isolation, f_partition_election], tested=[])
    await cluster.test_trace.start_subtest("Simlating network/speed problems for leader and starting election at node 2 ", features=spec)
    ts_1.block_network()
    logger.info('------------------ isolated leader, starting new election at node 2')
    await ts_2.start_campaign(authorized=True)
    await cluster.run_election()
    assert ts_1.get_role_name() == "LEADER"
    assert ts_2.get_role_name() == "LEADER"
    assert ts_3.get_leader_uri() == uri_2

    logger.info('------------------ 2 leaders, telling actual leader to run command')
    command_result = await cluster.run_command("add 1", 1)
    assert ts_2.operations.total == 2
    assert ts_3.operations.total == 2


    if discard:
        # Will discard the messages that were blocked 
        # so it looks like the network was broken
        # during that time.
        f_message_loss = registry.get_raft_feature("network_partition", "message_loss_recovery")
        spec = dict(used=[], tested=[f_message_loss])
        await cluster.test_trace.start_subtest("Letting old leader rejoin network, but losing any messages sent during problem period", features=spec)
        logger.info('------------------ Telling old leader to rejoin network with messages lost')
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
        logger.info('------------------ Telling old leader to rejoin network with messages still in queues')
        f_delayed_delivery = registry.get_raft_feature("network_partition", "delayed_message_delivery")
        spec = dict(used=[], tested=[f_delayed_delivery])
        await cluster.test_trace.start_subtest("Letting old leader rejoin network and delivering all lost messages", features=spec)

        ts_1.unblock_network(deliver=True)
        await cluster.deliver_all_pending()

    logger.debug('------------------ Command AppendEntries should get rejected -')

    
    # Section 5: Leader recovery via heartbeats  
    f_heartbeat_recovery = registry.get_raft_feature("log_replication", "heartbeat_only")
    spec = dict(used=[f_heartbeat_recovery], tested=[])
    await cluster.test_trace.start_subtest("New leader sending heartbeats", features=spec)
    logger.info('\n\n sending heartbeat, so old leader can catch up date\n\n')
    await ts_2.send_heartbeats()
    await cluster.deliver_all_pending()
    start_time = time.time()
    while time.time() - start_time < 0.1 and ts_1.operations.total < ts_2.operations.total:
        await asyncio.sleep(0.01)
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
    
    await cluster.test_trace.define_test("Testing command redirect after leader partition", logger=logger)
    
    # Section 1: Normal election to establish initial leader
    f_normal_election = registry.get_raft_feature("leader_election", "all_yes_votes.with_pre_vote")
    spec = dict(used=[f_normal_election], tested=[])
    await cluster.test_trace.start_test_prep("Normal election", features=spec)
    await cluster.start()
    await ts_1.start_campaign()
    await cluster.run_election()
    
    assert ts_1.get_role_name() == "LEADER"
    assert ts_2.get_leader_uri() == uri_1
    assert ts_3.get_leader_uri() == uri_1
    logger.info('------------------------ Election done')
    
    # Section 2: Normal command processing
    f_normal_command = registry.get_raft_feature("state_machine_command", "all_in_sync") 
    spec = dict(used=[f_normal_command], tested=[])
    logger.info('---------!!!!!!! starting comms')
    await cluster.test_trace.start_subtest("Running command normally", features=spec)
    command_result = await cluster.run_command("add 1", 1)
    assert ts_2.operations.total == 1
    assert ts_3.operations.total == 1
    logger.debug('------------------------ Correct command done')

    # Now we want to block all messages from the leader, then
    # trigger a follower to hold an election, wait for it to
    # win, then unblock the old leader, and then try another
    # command. The leader should figure out it doesn't lead
    # anymore and give back a redirect

    # Section 3: Network partition and new election
    f_leader_isolation = registry.get_raft_feature("network_partition", "leader_isolation")
    f_post_partition_election = registry.get_raft_feature("leader_election", "partition_recovery")
    spec = dict(used=[f_leader_isolation, f_post_partition_election], tested=[])
    logger.info('---------!!!!!!! stopping comms')
    await cluster.stop_auto_comms()
    await cluster.test_trace.start_subtest("Simlating network/speed problems for leader and starting election at node 2", features=spec)
    ts_1.block_network()
    logger.info('------------------ isolated leader, starting new election')
    await ts_2.start_campaign(authorized=True)
    await cluster.run_election()
    await cluster.deliver_all_pending()
    assert ts_1.get_role_name() == "LEADER"
    assert ts_2.get_role_name() == "LEADER"
    assert ts_3.get_leader_uri() == uri_2

    # Section 4: Command redirect after partition recovery  
    f_leader_discovery_redirect = registry.get_raft_feature("state_machine_command", "discovery_redirect")
    spec = dict(used=[], tested=[f_leader_discovery_redirect])
    await cluster.test_trace.start_subtest("Trying to run command at leader that is no longer connected", features=spec)
    
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
    case because everybody's log roles match, but Raft is conservative on this point and requires
    that the candidate reject an append entries of a lower term. This test is identical
    to test_command_after_heal_2 except that this version uses pre vote logic.

    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """
    cluster = cluster_maker(3)
    config = cluster.build_cluster_config(use_pre_vote=False)
    cluster.set_configs(config)
    await cluster.test_trace.define_test("Testing command processing after network heal with pre-vote")
    await cluster.test_trace.start_test_prep("Normal election")
    await cluster.start()
    await inner_command_after_heal(cluster, False)
    
async def test_command_after_heal_2(cluster_maker):
    """
    The goal for this test is for a candidate to receive an append entries message from a leader of a lower term.
    This can happen when a network partition resolves before a new election has completed and the 
    old leader sends a heartbeat out. There wouldn't be any problem with the candidate resigning in this
    case because everybody's log roles match, but Raft is conservative on this point and requires
    that the candidate reject an append entries of a lower term. This test is identical
    to test_command_after_heal_1 except that this version does not use pre vote logic.

    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """
    cluster = cluster_maker(3)
    config = cluster.build_cluster_config(use_pre_vote=False)
    cluster.set_configs(config)
    await cluster.start()
    await cluster.test_trace.define_test("Testing command processing after network heal without pre-vote")
    await cluster.test_trace.start_test_prep("Normal election")
    await inner_command_after_heal(cluster, False)
    
async def inner_command_after_heal(cluster, use_pre_vote):

    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]
    logger = logging.getLogger("test_code")

    await ts_1.start_campaign()
    await cluster.run_election()
    
    assert ts_1.get_role_name() == "LEADER"
    assert ts_2.get_leader_uri() == uri_1
    assert ts_3.get_leader_uri() == uri_1
    logger.info('-------------- Election done, about to split network leaving leader %s isolated ', uri_1)
    await cluster.test_trace.start_subtest("Node 1 is leader, splitting network to isolate it")
    part1 = {uri_1: ts_1}
    part2 = {uri_2: ts_2,
             uri_3: ts_3}
    await cluster.split_network([part1, part2])
    #logger.info('-------------- Split network done, starting election of %s', uri_2)
    # now ts_2 and ts_3 are alone, have ts_2
    await cluster.test_trace.start_subtest("Triggering node 2 to start an election, then healing network and triggering old leader to send heartbeats")
    await ts_2.start_campaign()
    assert ts_2.get_role_name() == "CANDIDATE"
    last_term = await ts_2.log.get_term()
    await cluster.unsplit()
    assert ts_1.get_role_name() == "LEADER"
    logger.info('-------------- telling reconnected old leader %s to send heartbeats, %s should reject in candidate',
                uri_1, uri_2)
    assert ts_1.get_role_name() == "LEADER"
    await ts_1.send_heartbeats()
    logger.info('-------------- old leader %s sent heartbeats', uri_1)
    await cluster.deliver_all_pending()

    # don't know how the election will turn out for sure, probably ts_2 will win
    # important thing is that ts_1 responded properly to higher term in response,
    # meaning that candidate reply did its thing
    assert await ts_1.log.get_term() == last_term
    
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

    await cluster.test_trace.define_test("Testing follower error during command execution")
    await cluster.test_trace.start_test_prep("Normal election")
    await cluster.start()
    await ts_1.start_campaign()

    await cluster.run_election()
    assert ts_1.get_role_name() == "LEADER"
    assert ts_1.get_leader_uri() == uri_1
    assert ts_2.get_leader_uri() == uri_1
    logger.info('------------------------ Election done')

    command_result = await cluster.run_command("add 1", 1)
    assert ts_1.operations.total == 1
    assert ts_2.operations.total == 1
    assert ts_3.operations.total == 1
    logger.debug('------------------------ Correct command done')
    await cluster.test_trace.start_subtest("Node 1 is leader, one command completed and all nodes in sync, rigging node 3 to explode processing next command")

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

    await cluster.test_trace.start_subtest("Second command succeed, but not at node3. Disarming bomb and sending hearbeats, should cause run and commit")
    # clear the trigger and run heartbeats, node 3 should rerun command and succeed
    ts_3.operations.explode = False
    await ts_1.send_heartbeats()
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

    await cluster.test_trace.define_test("Testing leader error during command execution")
    await cluster.test_trace.start_test_prep("Normal election")
    await cluster.start()
    await ts_1.start_campaign()

    await cluster.run_election()
    assert ts_1.get_role_name() == "LEADER"
    assert ts_1.get_leader_uri() == uri_1
    assert ts_2.get_leader_uri() == uri_1
    logger.info('------------------------ Election done')

    command_result = await cluster.run_command("add 1", 1)
    
    assert ts_1.operations.total == 1
    assert ts_2.operations.total == 1
    assert ts_3.operations.total == 1
    logger.debug('------------------------ Correct command done')

    await cluster.test_trace.start_subtest("Node 1 is leader, rigging it to explode on command and runnning command")

    # now arrange for leader to blow up.
    ts_1.operations.explode = True
    command_result = await cluster.run_command("add 1", timeout=0.01)
    assert command_result is not None
    assert command_result.error is not None
    
    await cluster.test_trace.start_subtest("Leader node 1 returned an error from command request, clearing trigger and sending heartbeats to retry")
    ts_1.operations.explode = False
    await ts_1.send_heartbeats()
    await cluster.deliver_all_pending()
    start_time = time.time()
    while time.time() - start_time < 0.1 and ts_1.operations.total < 2:
        await asyncio.sleep(0.0001)
    assert ts_1.operations.total == 2
    await cluster.test_trace.start_subtest("Leader node 1 retry succeeded, now need another heartbeat to trigger followers to apply and commit")
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

    await cluster.test_trace.define_test("Testing long catchup after network partition")
    await cluster.test_trace.start_test_prep("Normal election")
    await cluster.start()
    await ts_1.start_campaign()
    await cluster.run_election()
    
    assert ts_1.get_role_name() == "LEADER"
    assert ts_2.get_leader_uri() == uri_1
    assert ts_3.get_leader_uri() == uri_1
    logger.info('------------------------ Election done')
    logger.info('---------!!!!!!! starting comms')

    command_result = await cluster.run_command("add 1", 1)
    assert ts_2.operations.total == 1
    assert ts_3.operations.total == 1
    logger.debug('------------------------ Correct command done')


    # Make sure that the number of commands we send
    # now will require a couple of catchup messages, so
    # use the leader's runtime value

    cfg = ts_1.cluster_init_config
    loop_limit = cfg.max_entries_per_message * 2 + 2
    await cluster.test_trace.start_subtest(f"Node 1 is leader, partitioning network so that node 3 is isolated, then running {loop_limit} commands")
    
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
    logger.warning('------------------------ Surpressing logging')
    keep_active = ["test_commands_1", "Leader", "Follower"]
    with TemporaryLogControl(log_control, keep_active, 'ERROR') as tmplog:
        for i in range(loop_limit):
            command_result = await cluster.run_command("add 1", 1)
        total = ts_1.operations.total
        assert ts_2.operations.total == total
        assert ts_3.operations.total != total
    logger.warning('------------------------ Unsurpressing logging')
    # restore the loggers
    # will discard the messages that were blocked
    logger.debug('------------------ unblocking follower %s should catch up to total %d', uri_3, total)
    await cluster.test_trace.start_subtest("Commands run, now healing network and triggering a heartbeat, node 3 should catch up")
    #await cluster.deliver_all_pending()
    await cluster.unsplit()
    logger.info('---------!!!!!!! starting comms')
    #await cluster.start_auto_comms()
    await ts_1.send_heartbeats()

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

    await cluster.test_trace.define_test("Testing full catchup after follower crash")
    await cluster.test_trace.start_test_prep("Normal election")
    await cluster.start()
    await ts_1.start_campaign()
    await cluster.run_election()
    
    assert ts_2.get_leader_uri() == uri_1
    assert ts_3.get_leader_uri() == uri_1
    logger.info('------------------------ Election done')

    # Now we simulate the crash of  one follower,
    # then run a bunch of commands, restart the
    # follower and make sure that
    # the catchup process gets them all the messages

    await cluster.test_trace.start_subtest("Node 1 is leader, crashing node 3, then running two commands")
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


    await cluster.test_trace.start_subtest("Recovering node 3, then sending heartbeat which should result in catchup")
    await ts_3.recover_from_crash(save_log=False, save_ops=False)
    logger.info('------------------ restarting follower %s should catch up to total %d', uri_3, ts_1.operations.total)
    assert ts_3.operations.total != ts_1.operations.total
    logger.info('---------!!!!!!! starting comms')
    await ts_1.send_heartbeats()
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

    await cluster.test_trace.define_test("Testing follower error reporting during command execution")
    await cluster.test_trace.start_test_prep("Normal election")
    await cluster.start()
    await ts_1.start_campaign()
    await cluster.run_election()
    assert ts_1.get_role_name() == "LEADER"
    assert ts_2.get_leader_uri() == uri_1
    assert ts_3.get_leader_uri() == uri_1
    logger.info('------------------------ Election done')

    # Simulate crash of one follower, run a comand,
    # then restart it and send heartbeats, causing
    # it to try to catch up. However have the
    # "state machine" command pretend it had
    # an error. This should excersize some
    # error handling code, but then the next command
    # should go through without problem.

    logger.info('---------!!!!!!! spliting network ')
    await cluster.test_trace.start_subtest("Node 1 is leader, crashing node 3  and running a command")
    await ts_3.simulate_crash()
    logger.info('------------------ follower %s crashed, running', uri_3)
    
    command_result = await cluster.run_command("add 1", 1)
    assert ts_1.operations.total == 1
    assert ts_2.operations.total == ts_1.operations.total
    logger.debug('------------------------ Correct command 1 done')

    logger.info('------------------ restarted follower %s to hit error running command', uri_3)
    await cluster.test_trace.start_subtest("Setting return error trigger on node 3, recovering it, and running heartbeats")
    ts_3.operations.return_error = True
    await ts_3.recover_from_crash()
    logger.info('---------!!!!!!! starting comms')
    await ts_1.send_heartbeats()
    start_time = time.time()
    while time.time() - start_time < 0.5 and not ts_3.operations.reported_error:
        await cluster.deliver_all_pending()
    assert ts_3.operations.reported_error
    logger.info('------------------------ Error as expected, removing error insertion and trying again')
    await cluster.test_trace.start_subtest("Node 3 reported error, removing trigger and running heartbeats to retry")
    ts_3.operations.return_error = False
    await ts_1.send_heartbeats()
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

    """
    cluster = cluster_maker(3)
    cluster.set_configs()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]
    logger = logging.getLogger("test_code")

    await cluster.test_trace.define_test("Testing follower log rewrite after leader change")
    await cluster.test_trace.start_test_prep("Normal election")
    await cluster.start()
    await ts_1.start_campaign()
    await cluster.run_election()
    assert ts_1.get_role_name() == "LEADER"
    assert ts_2.get_leader_uri() == uri_1
    assert ts_3.get_leader_uri() == uri_1
    logger.info('------------------------ Election done')
    await cluster.start_auto_comms()
    running_total = 0
    last_index = await ts_1.log.get_last_index()

    await cluster.test_trace.start_subtest("Node 1 is leader, blocking network traffic to it like a partition and sending two commands")
    logger.info("---------!!!!!!! Blocking leader's network ")
    ts_1.block_network()
    logger.info('---------!!!!!!! Sending blocked leader two "sub 1" commands')
    command_result = await ts_1.run_command("sub 1", timeout=0.01)
    assert command_result.timeout_expired
    command_result = await ts_1.run_command("sub 1", timeout=0.01)
    assert command_result.timeout_expired
    assert await ts_1.log.get_last_index() == last_index + 2
    logger.debug('------------------------ Starting an election, favoring %s ---', uri_2)
    # now let the others do a new election
    await cluster.test_trace.start_subtest("Starting election at node 2, which it will win")
    await ts_2.start_campaign(authorized=True)
    await cluster.run_election()
    assert ts_2.get_role_name() == "LEADER"
    logger.debug('------------------------ Elected %s, demoting ex-leader %s ---', uri_2, uri_1)
    await cluster.test_trace.start_subtest("Demoting old leader to follower but not reconnecting it yet, running one command at new leader")
    # we do this now so that the cluster run_command method will not get confused
    # about which server is the leader
    await ts_1.do_demote_and_handle(None)
    assert ts_1.get_role_name() == "FOLLOWER"

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
    orig_rec_2 = await ts_1.log.read(first_relevant_index) # the first record is start term record
    orig_rec_3 = await ts_1.log.read(first_relevant_index + 1)
    logger.debug('------------------------ Unblocking ex-leader, should overwrite logs ---')
    await cluster.test_trace.start_subtest("Reconnecting old leader as follower, now it should have log records that have to be purged, sending heartbeats")
    ts_1.unblock_network() # discards missed messages
    await ts_2.send_heartbeats()
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
