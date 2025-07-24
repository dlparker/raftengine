#!/usr/bin/env python
import asyncio
import logging
import time
import os
from pathlib import Path
import pytest
from raftengine.messages.request_vote import RequestVoteMessage,RequestVoteResponseMessage
from raftengine.messages.pre_vote import PreVoteMessage, PreVoteResponseMessage
from raftengine.messages.append_entries import AppendEntriesMessage, AppendResponseMessage
from dev_tools.sequences import SNormalElection
from dev_tools.features import registry, FeatureRegistry

from dev_tools.pausing_cluster import PausingCluster, cluster_maker
from dev_tools.log_control import setup_logging

#extra_logging = [dict(name=__name__, level="debug"),]
#setup_logging(extra_logging)
default_level="error"
#default_level="debug"
log_control = setup_logging()
logger = logging.getLogger("test_code")
registry = FeatureRegistry.get_registry()

save_trace = True

async def test_election_1(cluster_maker):
    """

    This runs the election happy path, everybody has same state, only one server
    runs for leader, everybody responds correctly. It is written
    using the most granular control provided by the PausingServer
    class, controlling the message movement steps directly (for
    the most part). The cluster is three nodes. Prevote is disabled for this test.

    If some basic error is introduced in the election related code, it will
    show up here with the most detail.

    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """
    # Feature definitions for this test  
    f_election_no_prevote = registry.get_raft_feature("leader_election", "all_yes_votes.without_pre_vote")
    f_term_start_entry = registry.get_raft_feature("log_replication", "term_start_entry")
    f_append_entries_success = registry.get_raft_feature("log_replication", "normal_replication")

    cluster = cluster_maker(3)
    config = cluster.build_cluster_config(use_pre_vote=False)
    cluster.set_configs(config)
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]

    await cluster.test_trace.define_test("Testing basic election happy path with 3 nodes")
    
    spec = dict(used=[f_election_no_prevote], tested=[])
    await cluster.test_trace.start_subtest("Command triggering node one to start election", features=spec)
    await cluster.start()

    # tell first one to start election, should send request vote messages to other two
    await ts_1.start_campaign()
    await cluster.deliver_all_pending(out_only=True)
    assert len(ts_2.in_messages) == 1
    assert len(ts_3.in_messages) == 1
    assert ts_2.in_messages[0].get_code() == RequestVoteMessage.get_code()
    assert ts_3.in_messages[0].get_code() == RequestVoteMessage.get_code()

    # now deliver those, we should get two replies at first one, both with yes
    await ts_2.do_next_in_msg()
    await ts_2.do_next_out_msg()
    assert len(ts_1.in_messages) == 1
    await ts_3.do_next_in_msg()
    await ts_3.do_next_out_msg()
    assert len(ts_1.in_messages) == 2
    assert ts_1.in_messages[0].get_code() == RequestVoteResponseMessage.get_code()
    assert ts_1.in_messages[1].get_code() == RequestVoteResponseMessage.get_code()
    
    # now let candidate process votes, should then promote itself
    await ts_1.do_next_in_msg()
    assert ts_1.get_role_name() == "LEADER"
    await ts_1.do_next_in_msg()

    spec = dict(used=[f_term_start_entry], tested=[])
    await cluster.test_trace.start_subtest("Node 1 is now leader, so it should declare the new term with a TERM_START log record", features=spec)

    # leader should send append_entries to everyone else in cluster,
    # check for delivery pending
    start_time = time.time()
    while time.time() - start_time < 0.001 and len(ts_1.out_messages) == 0:
        await asyncio.sleep(0.00001)
    m1 = await ts_1.do_next_out_msg()
    assert m1
    assert m1.get_code() == AppendEntriesMessage.get_code()
    assert m1.receiver in [uri_2, uri_3]
    m2 = await ts_1.do_next_out_msg()
    assert m2
    assert m2.get_code() == AppendEntriesMessage.get_code()
    assert m2.receiver in [uri_2, uri_3]
    assert len(ts_2.in_messages) == 1
    assert len(ts_3.in_messages) == 1
    assert ts_2.in_messages[0].get_code() == AppendEntriesMessage.get_code()
    assert ts_3.in_messages[0].get_code() == AppendEntriesMessage.get_code()
    
    spec = dict(used=[f_append_entries_success], tested=[])
    await cluster.test_trace.start_subtest("Node 1 should get success replies to append entries from nodes 2 and 3", features=spec)
    # now deliver those, we should get two replies at first one,
    await ts_2.do_next_in_msg()
    await ts_2.do_next_out_msg()
    assert len(ts_1.in_messages) == 1
    await ts_3.do_next_in_msg()
    await ts_3.do_next_out_msg()
    assert len(ts_1.in_messages) == 2
    assert ts_1.in_messages[0].get_code() == AppendResponseMessage.get_code()
    assert ts_1.in_messages[1].get_code() == AppendResponseMessage.get_code()
    await ts_1.do_next_in_msg()
    await ts_1.do_next_in_msg()
    assert str(ts_1.get_role()) == "LEADER"

async def test_election_2(cluster_maker):
    """
    Just a simple test of first election with 5 servers, to ensure it
    works as well as 3 servers. Mostly pointless, but might catch an
    assumption in test support code that only three servers are used.
    Prevote is disabled for this test.
    
    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """
    # Feature definitions for this test
    f_election_no_prevote = registry.get_raft_feature("leader_election", "all_yes_votes.without_pre_vote")
    f_term_start_entry = registry.get_raft_feature("log_replication", "term_start_entry")
    f_heartbeat_commit = registry.get_raft_feature("log_replication", "heartbeat_commit_update")
    
    cluster = cluster_maker(5)
    config = cluster.build_cluster_config(use_pre_vote=False)
    cluster.set_configs(config)

    await cluster.test_trace.define_test("Testing basic election with 5 nodes")
    spec = dict(used=[f_election_no_prevote], tested=[])
    await cluster.test_trace.start_subtest("Command triggering node one to start election", features=spec)
    await cluster.start()
    uri_1, uri_2, uri_3, uri_4, uri_5 = cluster.node_uris
    ts_1, ts_2, ts_3, ts_4, ts_5 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3, uri_4, uri_5]]

    await ts_1.start_campaign()
    # vote requests, then vote responses
    await cluster.deliver_all_pending()
    assert ts_1.get_role_name() == "LEADER"
    
    spec = dict(used=[f_term_start_entry, f_heartbeat_commit], tested=[])
    await cluster.test_trace.start_subtest("Node 1 is leader, sending heartbeat so replies will tell us that followers did commit", features=spec)
    # append entries, then responses
    await cluster.deliver_all_pending()
    start_time = time.time()
    while time.time() - start_time < 0.01 and ts_2.get_leader_uri() != uri_1:
        await cluster.deliver_all_pending()
        await asyncio.sleep(0.00001)
    assert ts_2.get_leader_uri() == uri_1
    assert ts_3.get_leader_uri() == uri_1
    assert ts_4.get_leader_uri() == uri_1
    assert ts_5.get_leader_uri() == uri_1
    await ts_1.send_heartbeats()
    await cluster.deliver_all_pending()

    
async def test_reelection_1(cluster_maker):
    """
    Test of a hard triggered re-election, caused by using testing controls to directly
    demote the leader and directly trigger promotion to candidate on a different server.
    This is the simplest case of electing a new leader. Prevote is disabled for this test.
    
    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """
    # Feature definitions for this test
    f_election_no_prevote = registry.get_raft_feature("leader_election", "all_yes_votes.without_pre_vote")
    f_leader_demotion = registry.get_raft_feature("leader_election", "leader_demotion")
    f_follower_promotion = registry.get_raft_feature("leader_election", "follower_promotion")
    f_term_start_entry = registry.get_raft_feature("log_replication", "term_start_entry")
    
    cluster = cluster_maker(3)
    config = cluster.build_cluster_config(use_pre_vote=False)
    cluster.set_configs(config)

    await cluster.test_trace.define_test("Testing hard-triggered reelection with 3 nodes")
    spec = dict(used=[f_election_no_prevote], tested=[])
    await cluster.test_trace.start_subtest("Command triggering node one to start election", features=spec)
    await cluster.start()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]
    
    await ts_1.start_campaign()
    # vote requests, then vote responses
    await cluster.deliver_all_pending()
    assert ts_1.get_role_name() == "LEADER"
    # append entries, then responses
    start_time = time.time()
    while time.time() - start_time < 0.001 and ts_2.get_leader_uri() != uri_1:
        await cluster.deliver_all_pending()
        await asyncio.sleep(0.00001)
    assert ts_2.get_leader_uri() == uri_1
    assert ts_3.get_leader_uri() == uri_1

    spec = dict(used=[f_leader_demotion, f_follower_promotion, f_term_start_entry], tested=[])
    await cluster.test_trace.start_subtest("Node 1 is leader, demoting it and triggering leader_lost at node 2", features=spec)
    # now have leader resign, by telling it to become follower
    await ts_1.do_demote_and_handle(None)
    assert ts_1.get_role_name() == "FOLLOWER"
    # pretend timeout on heartbeat on only one, ensuring it will win
    await ts_2.do_leader_lost()
    await cluster.deliver_all_pending()
    assert ts_2.get_role_name() == "LEADER"
    assert ts_3.get_role_name() == "FOLLOWER"
    
async def test_reelection_2(cluster_maker):
    """
    Test of a hard triggered re-election, caused by directly
    demoting the leader and directly triggering a promotion to candidate
    on a different server. Identical to test_reelection_1 except it 
    uses 5 servers instead of three. Prevote is disabled for this test
    Just a guard against threshold or timing bugs that might trigger 
    on cluster size.

    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """
    # Feature definitions for this test
    f_election_no_prevote = registry.get_raft_feature("leader_election", "all_yes_votes.without_pre_vote")
    f_leader_demotion = registry.get_raft_feature("leader_election", "leader_demotion")
    f_follower_promotion = registry.get_raft_feature("leader_election", "follower_promotion")
    f_term_start_entry = registry.get_raft_feature("log_replication", "term_start_entry")
    
    cluster = cluster_maker(5)
    config = cluster.build_cluster_config(use_pre_vote=False)
    cluster.set_configs(config)

    await cluster.test_trace.define_test("Testing hard-triggered reelection with 5 nodes")
    spec = dict(used=[f_election_no_prevote], tested=[])
    await cluster.test_trace.start_subtest("Command triggering node one to start election", features=spec)
    await cluster.start()
    
    uri_1, uri_2, uri_3, uri_4, uri_5 = cluster.node_uris
    ts_1, ts_2, ts_3, ts_4, ts_5 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3, uri_4, uri_5]]

    await ts_1.start_campaign()
    # vote requests, then vote responses
    await cluster.deliver_all_pending()
    assert ts_1.get_role_name() == "LEADER"
    # append entries, then responses
    start_time = time.time()
    while time.time() - start_time < 0.001 and ts_2.get_leader_uri() != uri_1:
        await cluster.deliver_all_pending()
        await asyncio.sleep(0.00001)
    assert ts_2.get_leader_uri() == uri_1
    assert ts_3.get_leader_uri() == uri_1
    assert ts_4.get_leader_uri() == uri_1
    assert ts_5.get_leader_uri() == uri_1

    spec = dict(used=[f_leader_demotion, f_follower_promotion, f_term_start_entry], tested=[])
    await cluster.test_trace.start_subtest("Node 1 is leader, force demoting it and triggering leader_lost on node 2", features=spec)
    logger.debug("Node 1 is leader, force demoting it and triggering leader_lost on node 2")
    # now have leader resign, by telling it to become follower
    await ts_1.do_demote_and_handle(None)
    assert ts_1.get_role_name() == "FOLLOWER"
    # pretend timeout on heartbeat on only one followers, so it should win
    await ts_2.do_leader_lost()
    start_time = time.time()
    while time.time() - start_time < 0.01 and ts_1.get_leader_uri() != uri_2:
        await cluster.deliver_all_pending()
        await asyncio.sleep(0.00001)
    assert ts_2.get_role_name() == "LEADER"
    assert ts_1.get_role_name() == "FOLLOWER"
    assert ts_3.get_role_name() == "FOLLOWER"
    assert ts_1.get_leader_uri() == uri_2
    assert ts_3.get_leader_uri() == uri_2
    assert ts_4.get_leader_uri() == uri_2
    assert ts_5.get_leader_uri() == uri_2
    
async def test_reelection_3(cluster_maker):
    """
    This test ensures that elections resolve properly when all the nodes in the cluster
    are candidates and must apply the Raft logic for determining a winner. This involves
    the randomness of the election timeout principle.
    
    This test uses a mix of directly controlling nodes using the testing control system
    and normal timeout driven functions.

    The election timeout range for each node is set to values tuned to the desired result.
    The election timeout is a random value within a range, so to ensure that each node
    experiences the timeout in a specific order, the timeout ranges must not overlap.

    In this test the goal is to ensure that a specific node is elected leader,so
    that node gets a timeout range that is a couple of orders of magnitude (approximately)
    shorter than the other two nodes.

    During the first election, the timeouts are arranged to favor node 3. 
    Once the timeout configuration is complete, the network simulation is triggered to
    deliver messages until any one node reports that it is the leader and it must
    be node 3.
    
    Next the timeouts are adjusted to ensure that node 2 will win another election.
    Node 3 is demoted to follower. Then all three nodes are directed to start an election.
    The network simulation is triggered to deliver messages until any one node reports
    that it is the leader and it must be node 2.

    This second part with the reelection is the meat of the test, because the arrangement
    of actions will cause all three nodes to send out request vote messages, resulting
    in a split vote. So they have to walk through the steps of increasing the term and trying again.

    The Raft paper specifies that the candidate will wait for a timeout in the
    case of split votes, what we have here. This is important to prevent such
    votes from repeating indefinitely.

    """
    # Feature definitions for this test
    f_election_with_prevote = registry.get_raft_feature("leader_election", "all_yes_votes.with_pre_vote")
    f_timeout_driven_election = registry.get_raft_feature("leader_election", "timeout_driven_election")
    f_split_vote_resolution = registry.get_raft_feature("leader_election", "split_vote_resolution")
    f_leader_demotion = registry.get_raft_feature("leader_election", "leader_demotion") 
    f_term_start_entry = registry.get_raft_feature("log_replication", "term_start_entry")
    
    cluster = cluster_maker(3)
    cluster.set_configs()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]

    # make sure that we can control timeouts and get
    # things to happend that way

    # ensure that ts_3 wins first election

    cfg = ts_1.cluster_init_config
    cfg.election_timeout_min = 10.0
    cfg.election_timeout_max = 30.0
    await ts_1.change_cluster_config(cfg)
    await ts_2.change_cluster_config(cfg)
    # okay to do this, PausingServer makes a copy on change call
    cfg.election_timeout_min = 0.01
    cfg.election_timeout_max = 0.011
    await ts_3.change_cluster_config(cfg)


    await cluster.test_trace.define_test("Testing reelection with split votes and timeouts")
    spec = dict(used=[f_timeout_driven_election, f_election_with_prevote], tested=[])
    await cluster.test_trace.start_subtest("Command triggering node one to start election", features=spec)
    await cluster.start(timers_disabled=False)
    # give ts_3 time to timeout and start campaign
    start_time = time.time()
    leader = None
    while time.time() - start_time < 1 and leader is None:
        await asyncio.sleep(0.01)
        await cluster.deliver_all_pending()
        for ts in [ts_1, ts_2, ts_3]:
            if ts.get_role_name() == "LEADER":
                leader = ts
                break
    # vote requests, then vote responses
    assert leader == ts_3
    start_time = time.time()
    while time.time() - start_time < 0.01 and ts_1.get_leader_uri() != uri_3:
        await cluster.deliver_all_pending()
        await asyncio.sleep(0.00001)
    assert ts_1.get_leader_uri() == uri_3
    assert ts_2.get_leader_uri() == uri_3
    spec = dict(used=[f_leader_demotion, f_split_vote_resolution, f_term_start_entry], tested=[])
    await cluster.test_trace.start_subtest("Election complete, node 3 won as expected, setting up re-election to have node 2 win", features=spec)

    logger.warning('setting up re-election')
    # tell leader to resign and manually trigger elections on all the
    # servers, ts_2 should win because of timeout
    # ensure that ts_2 wins re-election

    cfg = ts_1.cluster_init_config
    cfg.election_timeout_min = 1
    cfg.election_timeout_max = 1.2
    await ts_1.change_cluster_config(cfg)
    # okay to do this, PausingServer makes a copy on change call
    cfg.election_timeout_min = 0.001
    cfg.election_timeout_max = 0.0011
    await ts_2.change_cluster_config(cfg)
    # okay to do this, PausingServer makes a copy on change call
    cfg.election_timeout_min = 1
    cfg.election_timeout_max = 1.2
    await ts_3.change_cluster_config(cfg)

    logger.warning('\n\n----------- ts_3 starting campaign\n\n')
    await ts_3.do_demote_and_handle(None)
    await ts_3.start_campaign()
    logger.warning('leader ts_3 demoted and campaign started')
    # ts_2 started last, but should win and raise term to 3 because of timeout
    
    logger.warning('\n\n----------- ts_1 starting campaign\n\n')
    await ts_1.start_campaign()
    logger.warning('\n\n----------- ts_2 starting campaign, delivering messages\n\n')
    await ts_2.start_campaign()
    await cluster.deliver_all_pending()
    logger.warning('waiting for re-election to happend')
    start_time = time.time()
    while time.time() - start_time < 0.01:
        await cluster.deliver_all_pending()
        if ts_2.get_role_name() == "LEADER":
            break
        await asyncio.sleep(0.0001)
        
    start_time = time.time()
    while time.time() - start_time < 0.01 and ts_1.get_leader_uri() != uri_2:
        await cluster.deliver_all_pending()
        await asyncio.sleep(0.00001)
    assert ts_2.get_role_name() == "LEADER"
    assert ts_1.get_leader_uri() == uri_2
    assert ts_3.get_leader_uri() == uri_2
    await cluster.deliver_all_pending()

    
async def test_pre_election_1(cluster_maker):
    """

    This runs the election happy path, with prevote enabled
    everybody has same state, only one server
    runs for leader, everybody responds correctly. It is written
    using the most granular control provided by the PausingServer
    class, controlling the message movement steps directly (for
    the most part). The cluster is three nodes.

    If some basic error is introduced in the election related code, it will
    show up here with the most detail.

    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """
    # Feature definitions for this test
    f_election_with_prevote = registry.get_raft_feature("leader_election", "all_yes_votes.with_pre_vote")
    f_term_start_entry = registry.get_raft_feature("log_replication", "term_start_entry")
    f_append_entries_success = registry.get_raft_feature("log_replication", "normal_replication")

    cluster = cluster_maker(3)
    cluster.set_configs()

    await cluster.test_trace.define_test("Testing election with pre-vote enabled")
    spec = dict(used=[f_election_with_prevote], tested=[])
    await cluster.test_trace.start_subtest("Command triggering node one to start election", features=spec)
    await cluster.start()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]

    # tell first one to start election, should send request vote messages to other two
    await ts_1.start_campaign()
    await cluster.deliver_all_pending(out_only=True)
    assert len(ts_2.in_messages) == 1
    assert len(ts_3.in_messages) == 1
    assert ts_2.in_messages[0].get_code() == PreVoteMessage.get_code()
    assert ts_3.in_messages[0].get_code() == PreVoteMessage.get_code()

    # now deliver those, we should get two replies at first one, both with yes
    await ts_2.do_next_in_msg()
    await ts_2.do_next_out_msg()
    assert len(ts_1.in_messages) == 1
    await ts_3.do_next_in_msg()
    await ts_3.do_next_out_msg()
    assert len(ts_1.in_messages) == 2
    assert ts_1.in_messages[0].get_code() == PreVoteResponseMessage.get_code()
    assert ts_1.in_messages[1].get_code() == PreVoteResponseMessage.get_code()
    assert "v=True" in str(ts_1.in_messages[0])
    assert "v=True" in str(ts_1.in_messages[1])
    await ts_1.do_next_in_msg()
    await ts_1.do_next_in_msg()
    
    await cluster.deliver_all_pending(out_only=True)
    assert len(ts_2.in_messages) == 1
    assert len(ts_3.in_messages) == 1
    assert ts_2.in_messages[0].get_code() == RequestVoteMessage.get_code()
    assert ts_3.in_messages[0].get_code() == RequestVoteMessage.get_code()

    # now deliver those, we should get two replies at first one, both with yes
    await ts_2.do_next_in_msg()
    await ts_2.do_next_out_msg()
    assert len(ts_1.in_messages) == 1
    await ts_3.do_next_in_msg()
    await ts_3.do_next_out_msg()
    assert len(ts_1.in_messages) == 2
    assert ts_1.in_messages[0].get_code() == RequestVoteResponseMessage.get_code()
    assert ts_1.in_messages[1].get_code() == RequestVoteResponseMessage.get_code()
    
    # now let candidate process votes, should then promote itself
    await ts_1.do_next_in_msg()
    await ts_1.do_next_in_msg()
    assert ts_1.get_role_name() == "LEADER"

    spec = dict(used=[f_term_start_entry], tested=[])
    await cluster.test_trace.start_subtest("Node 1 is now leader, so it should declare the new term with a TERM_START log record", features=spec)

    # leader should send append_entries to everyone else in cluster,
    # check for delivery pending
    await ts_1.do_next_out_msg()
    await ts_1.do_next_out_msg()
    start_time = time.time()
    while time.time() - start_time < 0.02 and (len(ts_2.in_messages) == 0 or len(ts_3.in_messages) == 0):
        await asyncio.sleep(0.00001)
        if len(ts_1.out_messages) > 0:
            await ts_1.do_next_out_msg()
        
    assert len(ts_2.in_messages) == 1
    assert len(ts_3.in_messages) == 1
    assert ts_2.in_messages[0].get_code() == AppendEntriesMessage.get_code()
    assert ts_3.in_messages[0].get_code() == AppendEntriesMessage.get_code()
    
    spec = dict(used=[f_append_entries_success], tested=[])
    await cluster.test_trace.start_subtest("Node 1 should get success replies to append entries from nodes 2 and 3", features=spec)
    # now deliver those, we should get two replies at first one,
    await ts_2.do_next_in_msg()
    await ts_2.do_next_out_msg()
    assert len(ts_1.in_messages) == 1
    await ts_3.do_next_in_msg()
    await ts_3.do_next_out_msg()
    assert len(ts_1.in_messages) == 2
    assert ts_1.in_messages[0].get_code() == AppendResponseMessage.get_code()
    assert ts_1.in_messages[1].get_code() == AppendResponseMessage.get_code()
    await ts_1.do_next_in_msg()
    await ts_1.do_next_in_msg()
    
    
async def test_pre_vote_reject_1(cluster_maker):
    """

    This runs a regular election, then tells one node to start a campain. It should get
    no votes from both leader and follower.

    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """
    # Feature definitions for this test
    f_election_with_prevote = registry.get_raft_feature("leader_election", "all_yes_votes.with_pre_vote")
    f_prevote_rejection = registry.get_raft_feature("leader_election", "prevote_rejection")
    f_heartbeat_authority = registry.get_raft_feature("log_replication", "heartbeat_authority")

    cluster = cluster_maker(3)
    cluster.set_configs()

    await cluster.test_trace.define_test("Testing pre-vote rejection after normal election")
    spec = dict(used=[f_election_with_prevote], tested=[])
    await cluster.test_trace.start_subtest("Command triggering node one to start election", features=spec)
    await cluster.start()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]

    # tell first one to start election, should send request vote messages to other two
    await ts_1.start_campaign()

    sequence = SNormalElection(cluster, 1)
    await cluster.run_sequence(sequence)
    

    assert ts_1.get_role_name() == "LEADER"
    assert ts_2.get_leader_uri() == uri_1
    assert ts_3.get_leader_uri() == uri_1


    spec = dict(used=[f_prevote_rejection, f_heartbeat_authority], tested=[])
    await cluster.test_trace.start_subtest("Node 3 starting campaign, should get no votes only", features=spec)
    await ts_3.start_campaign()
    await cluster.deliver_all_pending(out_only=True)
    assert len(ts_1.in_messages) == 1
    assert len(ts_2.in_messages) == 1
    assert ts_1.in_messages[0].get_code() == PreVoteMessage.get_code()
    assert ts_2.in_messages[0].get_code() == PreVoteMessage.get_code()
    # now deliver those, we should get two replies at first one, both with yes
    await ts_1.do_next_in_msg()
    await ts_1.do_next_out_msg()
    assert len(ts_3.in_messages) == 1
    await ts_2.do_next_in_msg()
    await ts_2.do_next_out_msg()
    assert len(ts_3.in_messages) == 2
    assert ts_3.in_messages[0].get_code() == PreVoteResponseMessage.get_code()
    assert ts_3.in_messages[1].get_code() == PreVoteResponseMessage.get_code()
    assert "v=False" in str(ts_3.in_messages[0])
    assert "v=False" in str(ts_3.in_messages[1])
    await ts_1.send_heartbeats()
    await cluster.deliver_all_pending()
    assert ts_3.get_role_name() == "FOLLOWER"
    assert ts_3.get_leader_uri() == uri_1
