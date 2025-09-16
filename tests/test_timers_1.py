#!/usr/bin/env python
import asyncio
import logging
import time
from pathlib import Path
import pytest
from raftengine.messages.append_entries import AppendEntriesMessage, AppendResponseMessage


from dev_tools.log_control import setup_logging
from dev_tools.pausing_cluster import cluster_maker
from dev_tools.sequences import SNormalElection
from dev_tools.features import FeatureRegistry

#extra_logging = [dict(name=__name__, level="debug"),]
#setup_logging(extra_logging)
default_level="error"
#default_level="debug"
log_control = setup_logging()
logger = logging.getLogger("test_code")
registry = FeatureRegistry.get_registry()


async def test_heartbeat_1(cluster_maker):
    """
    Simple test that heartbeat timer causes heartbeat messages.

    Starts with a normal election but with timers enabled, then just loops
    waiting for append entry messages to be sent to followers. 

    """
    
    # Feature definitions for heartbeat timer functionality
    f_election = registry.get_raft_feature("leader_election", "all_yes_votes.with_pre_vote")
    f_heartbeat_timer = registry.get_raft_feature("timers", "heartbeat_timer")
    f_automatic_heartbeats = registry.get_raft_feature("timers", "automatic_heartbeats")
    f_heartbeat_processing = registry.get_raft_feature("log_replication", "heartbeat_processing")
    
    cluster = cluster_maker(3)
    heartbeat_period = 0.01
    config = cluster.build_cluster_config(heartbeat_period=heartbeat_period)
    cluster.set_configs(config)
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]

    await cluster.test_trace.define_test("Testing heartbeat timer causing heartbeat messages", logger=logger)
    
    spec = dict(used=[f_election], tested=[])
    await cluster.test_trace.start_test_prep("Normal election with timers enabled", features=spec)
    await cluster.start(timers_disabled=False)
    await ts_3.start_campaign()

    sequence = SNormalElection(cluster, 1)
    await cluster.run_sequence(sequence)
    assert ts_3.get_role_name() == "LEADER"
    assert ts_1.get_leader_uri() == uri_3
    assert ts_2.get_leader_uri() == uri_3

    spec = dict(used=[f_election], tested=[f_heartbeat_timer, f_automatic_heartbeats, f_heartbeat_processing])
    await cluster.test_trace.start_subtest("Testing automatic heartbeat timer functionality", features=spec)
    # Test that heartbeat happens in approx expected time
    start_time = time.time()
    full_in_ledger = []
    full_out_ledger = []
    fraction = heartbeat_period/10.0
    while time.time() - start_time < heartbeat_period  * 2:
        deliver_res = await cluster.deliver_all_pending()
        full_in_ledger += deliver_res['in_ledger']
        full_out_ledger += deliver_res['out_ledger']
        if len(full_in_ledger) > 1 and len(full_out_ledger) > 1:
            break
        await asyncio.sleep(fraction)
        
    assert full_out_ledger[0].get_code() == AppendEntriesMessage.get_code()
    assert full_in_ledger[0].get_code() == AppendEntriesMessage.get_code()
    assert full_out_ledger[1].get_code() == AppendResponseMessage.get_code()
    assert full_in_ledger[1].get_code() == AppendResponseMessage.get_code()
    await cluster.deliver_all_pending()

async def test_heartbeat_2(cluster_maker):
    """
    Tests to make sure that correct heartbeat timer and election timeout
    values do not result in an election if everything is allowed to run
    for more than the election timeout value.

    Test starts with a normal election with timers on, then the
    auto transport is enabled and a time period equal to twice the
    election_timeout max value is allowed to pass. If the leader
    is still the leader and the term is still the term, then party.
    """
    
    # Feature definitions for timer coordination
    f_election = registry.get_raft_feature("leader_election", "all_yes_votes.with_pre_vote")
    f_heartbeat_timer = registry.get_raft_feature("timers", "heartbeat_timer")
    f_election_timeout = registry.get_raft_feature("timers", "election_timeout")
    f_timeout_prevention = registry.get_raft_feature("timers", "election_timeout_prevention")
    
    cluster = cluster_maker(3)
    heartbeat_period = 0.02
    election_timeout_min = 0.1
    election_timeout_max = 0.11
    config = cluster.build_cluster_config(heartbeat_period=heartbeat_period,
                                          election_timeout_min=election_timeout_min, 
                                          election_timeout_max=election_timeout_max)
                                          
    cluster.set_configs(config)
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]

    await cluster.test_trace.define_test("Testing correct timer values preventing unnecessary elections", logger=logger)
    
    spec = dict(used=[f_election], tested=[])
    await cluster.test_trace.start_test_prep("Normal election with configured timers", features=spec)
    await cluster.start(timers_disabled=False)
    await ts_3.start_campaign()

    sequence = SNormalElection(cluster, 1)
    await cluster.run_sequence(sequence)
    term =  await ts_3.log.get_term()
    assert ts_3.get_role_name() == "LEADER"
    assert ts_1.get_leader_uri() == uri_3
    assert ts_2.get_leader_uri() == uri_3
    
    spec = dict(used=[f_heartbeat_timer, f_election_timeout], tested=[f_timeout_prevention])
    await cluster.test_trace.start_subtest(f"Node 3 is leader, starting auto comms and waiting for {election_timeout_max * 2}", features=spec)
    await cluster.start_auto_comms()
    # make sure running for a time exceeding the timeout does not
    # cause a leader lost situation
    fraction = election_timeout_max/5.0
    start_time = time.time()
    while time.time() - start_time < election_timeout_max * 2:
        await asyncio.sleep(fraction)

    assert ts_3.get_role_name() == "LEADER"
    assert ts_1.get_leader_uri() == uri_3
    assert ts_2.get_leader_uri() == uri_3
    assert term == await ts_3.log.get_term()
    await cluster.stop_auto_comms()
        
async def test_lost_leader_1(cluster_maker):
    """
    This tests to ensure that timers will cause lost leader condition and a new election when needed.
    
    This is done by setting timeout values so that heartbeat is longer than max election timeout,
    guaranteeing that at least one node will panic and run for office.

    This test has pre_vote disabled to make it easier to track the new election
    
    """
    
    # Feature definitions - leader failure detection and automatic re-election
    f_election_timeout = registry.get_raft_feature("timers", "election_timeout")
    f_leader_failure_detection = registry.get_raft_feature("timers", "leader_failure_detection")
    f_automated_election = registry.get_raft_feature("leader_election", "automated_election_process")
    f_heartbeat_timer = registry.get_raft_feature("timers", "heartbeat_timer")
    f_role_transitions = registry.get_raft_feature("leader_election", "role_transitions")
    f_term_advancement = registry.get_raft_feature("leader_election", "term_advancement")
    
    cluster = cluster_maker(3)
    # make leader too slow, will cause re-election
    heartbeat_period = 0.2
    election_timeout_min = 0.02
    election_timeout_max = 0.05
    config = cluster.build_cluster_config(heartbeat_period=heartbeat_period,
                                          election_timeout_min=election_timeout_min, 
                                          election_timeout_max=election_timeout_max,
                                          use_pre_vote=False)
    cluster.set_configs(config)
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]

    await cluster.test_trace.define_test("Testing timers causing lost leader condition and new election")
    
    # Section 1: Initial election establishment with slow heartbeat configuration
    spec = dict(used=[f_automated_election, f_heartbeat_timer], tested=[])
    await cluster.test_trace.start_test_prep("Normal election", features=spec)
    await cluster.start(timers_disabled=False)
    await ts_3.start_campaign()
    await cluster.deliver_all_pending()
    await cluster.run_election()
    await cluster.deliver_all_pending()
    assert ts_3.get_role_name() == "LEADER"
    assert ts_1.get_leader_uri() == uri_3
    assert ts_2.get_leader_uri() == uri_3
    await ts_3.do_demote_and_handle(None)

    # Section 2: Leader failure detection and automatic re-election via timeout
    spec = dict(used=[f_election_timeout], tested=[f_leader_failure_detection, f_role_transitions, f_term_advancement])
    await cluster.test_trace.start_subtest("Node 3 is leader, waiting for someone to timeout and start an election", features=spec)
    # Test that election starts in appoximately the leader_lost timeout
    start_time = time.time()
    fraction = election_timeout_max/10.0
    while time.time() - start_time < election_timeout_max * 3:
        await cluster.deliver_all_pending()
        if (ts_1.get_role_name() != "FOLLOWER"
            or ts_2.get_role_name()  != "FOLLOWER"
            or ts_3.get_role_name()  != "FOLLOWER"):
            break
        await asyncio.sleep(fraction)
        await cluster.deliver_all_pending()
    assert (ts_1.get_role_name()  != "FOLLOWER"
            or ts_2.get_role_name()  != "FOLLOWER"
            or ts_3.get_role_name()  != "FOLLOWER")

    changed = None
    for ts in ts_1, ts_2, ts_3:
        if ts.get_role_name()  == "LEADER" or ts.get_role_name() == "CANDIDATE":
            changed = ts
            break
    assert changed is not None
    assert await changed.log.get_term() > 1
    
    
async def test_candidate_timeout_1(cluster_maker):
    """
    Test to ensure that a candidate will give up on campaign if no resolution happens
    by election timeout time, and then start a new election. This is with pre vote disabled.

    Test begins with a normal election with test-like timer values but timers disabled.

    Then node1 and node3 have their networks switch to blocked mode so they won't process
    any messages. Node 1, the leader is also forced to retire. So now there are two
    followers but node 2 can't reach them.

    Next auto transport is enabled and node2 has its timers enabled. Things are allowed
    to run long enough that node 2 should timeout and try again. The value of
    node2 term will indicate when that has happend.

    When that works, the other nodes are unblocked and the election is allowed to proceed.
    
    """
    
    # Feature definitions - candidate timeout and election retry mechanisms
    f_candidate_timeout = registry.get_raft_feature("timers", "candidate_timeout")
    f_election_timeout_retry = registry.get_raft_feature("leader_election", "election_timeout_retry")
    f_automated_election = registry.get_raft_feature("leader_election", "automated_election_process")
    f_network_blocking = registry.get_raft_feature("test_infrastructure", "network_blocking")
    f_term_advancement = registry.get_raft_feature("leader_election", "term_advancement")
    f_role_transitions = registry.get_raft_feature("leader_election", "role_transitions")
    f_timer_operations = registry.get_raft_feature("test_infrastructure", "timer_operations")
    
    cluster = cluster_maker(3)
    heartbeat_period = 0.001
    election_timeout_min = 0.009
    election_timeout_max = 0.011
    config = cluster.build_cluster_config(heartbeat_period=heartbeat_period,
                                          election_timeout_min=election_timeout_min, 
                                          election_timeout_max=election_timeout_max,
                                          use_pre_vote=False)
    cluster.set_configs(config)
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]

    await cluster.test_trace.define_test("Testing candidate timeout and new election start")
    
    # Section 1: Initial election establishment
    spec = dict(used=[f_automated_election], tested=[])
    await cluster.test_trace.start_test_prep("Normal election", features=spec)

    await cluster.start(timers_disabled=True)
    await ts_1.start_campaign()
    await cluster.run_election()

    assert ts_1.get_role_name() == "LEADER"
    assert ts_2.get_leader_uri() == uri_1
    assert ts_2.get_leader_uri() == uri_1

    # Now arrange another election and make sure that the candidate
    # experiences a timeout, no votes in required time. It should
    # incr the term and retry so we can monitor by term value
    # Section 2: Network isolation setup for candidate timeout testing
    spec = dict(used=[f_network_blocking, f_role_transitions], tested=[])
    await cluster.test_trace.start_subtest("Node 1 is leader, blocking comms to node 1 and node 2, and demoting node 1 to follower", features=spec)
    orig_term = await ts_2.log.get_term()
    ts_1.block_network()
    # we don't want ts_3 to vote yes, so block it too
    ts_3.block_network()
    await ts_1.do_demote_and_handle(None)
    # Section 3: Isolated candidate election initiation with timer enable
    spec = dict(used=[f_timer_operations], tested=[f_term_advancement])
    await cluster.test_trace.start_subtest("Starting auto comms, enabling timers at node 2 and it to start election", features=spec)
    await cluster.start_auto_comms()
    await ts_2.enable_timers()
    start_time = time.time()
    fraction = election_timeout_max/50.0
    while (time.time() - start_time < election_timeout_max  * 2
           and await ts_2.log.get_term() == orig_term):
        await asyncio.sleep(fraction)
    term_now = await ts_2.log.get_term()
    assert term_now != orig_term
    # Section 4: Candidate timeout detection and election retry
    spec = dict(used=[], tested=[f_candidate_timeout, f_election_timeout_retry])
    await cluster.test_trace.start_subtest("Node 2 started election, waiting for it to timeout", features=spec)
    if term_now == orig_term + 1:
        # not done yet, just running as candidate for first time,
        start_time = time.time()
        while (time.time() - start_time < election_timeout_max  * 2
               and await ts_2.log.get_term() == term_now):
            await asyncio.sleep(fraction)
    final_term = await ts_2.log.get_term()
    assert final_term == orig_term + 2

    # Section 5: Network restoration and successful election completion
    spec = dict(used=[f_network_blocking, f_automated_election], tested=[])
    await cluster.test_trace.start_subtest("Node 2 election timeout detected, enabling other nodes to let election finish", features=spec)
    ts_1.unblock_network()
    ts_3.unblock_network()
    # now make sure it can win
    start_time = time.time()
    while (time.time() - start_time < election_timeout_max  * 2
           and ts_2.get_role_name()  != "LEADER"):
            await asyncio.sleep(fraction)
    assert ts_2.get_role_name()  == "LEADER"
    
    await cluster.stop_auto_comms()
