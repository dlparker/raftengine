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
from dev_tools.servers import SNormalElection

from dev_tools.servers import PausingCluster, cluster_maker
from dev_tools.servers import setup_logging

#extra_logging = [dict(name=__name__, level="debug"),]
#setup_logging(extra_logging)
default_level="error"
#default_level="debug"
setup_logging(default_level=default_level)
logger = logging.getLogger("test_code")

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

    cluster = cluster_maker(3)
    config = cluster.build_cluster_config(use_pre_vote=False)
    cluster.set_configs(config)
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]

    cluster.test_trace.start_subtest("Node 1 starts campaign, nodes 2 and 3 should get and reply 'yes' to request vote messages",
                                     test_path_str=str('/'.join(Path(__file__).parts[-2:])),
                                     test_doc_string=test_election_1.__doc__)
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
    await ts_1.do_next_in_msg()
    assert ts_1.get_role_name() == "LEADER"

    cluster.test_trace.start_subtest("Node 1 is now leader, so it should declare the new term with a TERM_START log record")

    # leader should send append_entries to everyone else in cluster,
    # check for delivery pending
    await ts_1.do_next_out_msg()
    await ts_1.do_next_out_msg()
    assert len(ts_2.in_messages) == 1
    assert len(ts_3.in_messages) == 1
    assert ts_2.in_messages[0].get_code() == AppendEntriesMessage.get_code()
    assert ts_3.in_messages[0].get_code() == AppendEntriesMessage.get_code()
    
    cluster.test_trace.start_subtest("Node 1 should get success replies to append entries from nodes 2 and 3")
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


async def test_election_2(cluster_maker):
    """
    Just a simple test of first election with 5 servers, to ensure it
    works as well as 3 servers. Mostly pointless, but might catch an
    assumption in test support code that only three servers are used.
    Prevote is disabled for this test.
    
    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """
    
    cluster = cluster_maker(5)
    config = cluster.build_cluster_config(use_pre_vote=False)
    cluster.set_configs(config)

    cluster.test_trace.start_subtest("Starting election at node 1 of 5",
                                     test_path_str=str('/'.join(Path(__file__).parts[-2:])),
                                     test_doc_string=test_election_2.__doc__)
    await cluster.start()
    uri_1, uri_2, uri_3, uri_4, uri_5 = cluster.node_uris
    ts_1, ts_2, ts_3, ts_4, ts_5 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3, uri_4, uri_5]]

    await ts_1.start_campaign()
    # vote requests, then vote responses
    await cluster.deliver_all_pending()
    assert ts_1.get_role_name() == "LEADER"
    cluster.test_trace.start_subtest("Node 1 is leader, sending heartbeat so replies will tell us that followers did commit")
    # append entries, then responses
    await cluster.deliver_all_pending()
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
    cluster = cluster_maker(3)
    config = cluster.build_cluster_config(use_pre_vote=False)
    cluster.set_configs(config)

    cluster.test_trace.start_subtest("Initial election, normal",
                                     test_path_str=str('/'.join(Path(__file__).parts[-2:])),
                                     test_doc_string=test_reelection_1.__doc__)
    await cluster.start()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]
    
    await ts_1.start_campaign()
    # vote requests, then vote responses
    await cluster.deliver_all_pending()
    assert ts_1.get_role_name() == "LEADER"
    # append entries, then responses
    await cluster.deliver_all_pending()
    assert ts_2.get_leader_uri() == uri_1
    assert ts_3.get_leader_uri() == uri_1

    cluster.test_trace.start_subtest("Node 1 is leader, demoting it and triggering leader_lost at node 2")
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
    cluster = cluster_maker(5)
    config = cluster.build_cluster_config(use_pre_vote=False)
    cluster.set_configs(config)

    cluster.test_trace.start_subtest("Initial election, normal",
                                     test_path_str=str('/'.join(Path(__file__).parts[-2:])),
                                     test_doc_string=test_reelection_2.__doc__)
    await cluster.start()
    
    uri_1, uri_2, uri_3, uri_4, uri_5 = cluster.node_uris
    ts_1, ts_2, ts_3, ts_4, ts_5 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3, uri_4, uri_5]]

    await ts_1.start_campaign()
    # vote requests, then vote responses
    await cluster.deliver_all_pending()
    assert ts_1.get_role_name() == "LEADER"
    # append entries, then responses
    await cluster.deliver_all_pending()
    assert ts_2.get_leader_uri() == uri_1
    assert ts_3.get_leader_uri() == uri_1
    assert ts_4.get_leader_uri() == uri_1
    assert ts_5.get_leader_uri() == uri_1

    cluster.test_trace.start_subtest("Node 1 is leader, force demoting it and triggering leader_lost on node 2")
    logger.debug("Node 1 is leader, force demoting it and triggering leader_lost on node 2")
    # now have leader resign, by telling it to become follower
    await ts_1.do_demote_and_handle(None)
    assert ts_1.get_role_name() == "FOLLOWER"
    # pretend timeout on heartbeat on only one followers, so it should win
    await ts_2.do_leader_lost()
    await cluster.deliver_all_pending()
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
    
    
    cluster = cluster_maker(3)
    cluster.set_configs()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]

    # make sure that we can control timeouts and get
    # things to happend that way

    # ensure that ts_3 wins first election

    cfg = ts_1.cluster_config
    cfg.election_timeout_min = 0.90
    cfg.election_timeout_max = 1.0
    ts_1.change_cluster_config(cfg)
    ts_2.change_cluster_config(cfg)
    # okay to do this, PausingServer makes a copy on change call
    cfg.election_timeout_min = 0.01
    cfg.election_timeout_max = 0.011
    ts_3.change_cluster_config(cfg)


    cluster.test_trace.start_subtest("Starting cluster with election timeout timers active, biased for node 3 to win",
                                     test_path_str=str('/'.join(Path(__file__).parts[-2:])),
                                     test_doc_string=test_reelection_3.__doc__)
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
    assert ts_1.get_leader_uri() == uri_3
    assert ts_2.get_leader_uri() == uri_3
    cluster.test_trace.start_subtest("Election complete, node 3 won as expected, setting up re-election to have node 2 win")

    logger.warning('setting up re-election')
    # tell leader to resign and manually trigger elections on all the
    # servers, ts_2 should win because of timeout
    # ensure that ts_2 wins re-election

    cfg = ts_1.cluster_config
    cfg.election_timeout_min = 1
    cfg.election_timeout_max = 1.2
    ts_1.change_cluster_config(cfg)
    # okay to do this, PausingServer makes a copy on change call
    cfg.election_timeout_min = 0.001
    cfg.election_timeout_max = 0.0011
    ts_2.change_cluster_config(cfg)
    # okay to do this, PausingServer makes a copy on change call
    cfg.election_timeout_min = 1
    cfg.election_timeout_max = 1.2
    ts_3.change_cluster_config(cfg)

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

    cluster = cluster_maker(3)
    cluster.set_configs()

    cluster.test_trace.start_subtest("Node 1 starts campaign, nodes 2 and 3 should get and reply 'yes' to request vote messages",
                                     test_path_str=str('/'.join(Path(__file__).parts[-2:])),
                                     test_doc_string=test_pre_election_1.__doc__)
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

    cluster.test_trace.start_subtest("Node 1 is now leader, so it should declare the new term with a TERM_START log record")

    # leader should send append_entries to everyone else in cluster,
    # check for delivery pending
    await ts_1.do_next_out_msg()
    await ts_1.do_next_out_msg()
    assert len(ts_2.in_messages) == 1
    assert len(ts_3.in_messages) == 1
    assert ts_2.in_messages[0].get_code() == AppendEntriesMessage.get_code()
    assert ts_3.in_messages[0].get_code() == AppendEntriesMessage.get_code()
    
    cluster.test_trace.start_subtest("Node 1 should get success replies to append entries from nodes 2 and 3")
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

    cluster = cluster_maker(3)
    cluster.set_configs()

    cluster.test_trace.start_subtest("Node 1 starts campaign and normal election is run",
                                     test_path_str=str('/'.join(Path(__file__).parts[-2:])),
                                     test_doc_string=test_pre_vote_reject_1.__doc__)
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


    cluster.test_trace.start_subtest("Node 3 starting campaign, should get no votes only")
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
    

    
    
