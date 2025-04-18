#!/usr/bin/env python
import asyncio
import logging
import time
import json
from pathlib import Path
import pytest
from raftengine.messages.request_vote import RequestVoteMessage,RequestVoteResponseMessage
from raftengine.messages.append_entries import AppendEntriesMessage, AppendResponseMessage

from dev_tools.servers import WhenElectionDone, SNormalElection
from dev_tools.servers import PausingCluster, cluster_maker
from dev_tools.servers import setup_logging

#extra_logging = [dict(name=__name__, level="debug"),]
#setup_logging(extra_logging)
setup_logging()
logger = logging.getLogger("test_code")

async def test_restart_during_heartbeat(cluster_maker):
    """
    This tests that the message problem logging mechanism works.

    The test begins with a normal election. After it is complete, the leader sends out
    heartbeat messages, but we delay delivery and then force the leader to resign.

    We resume delivery, which results in the ex-leader receiving append response messages. Since
    it is now a follower, these messages are rejected, and the fact is logged in the message
    problem log. We check the log to make sure we have two entries, one for each follower.

    Next we trigger the leader to start a new election, which it will win.

    When the election is complete, we insert a generated vote response message into the
    leader's input queue. It does not expect this so it rejects it and logs it. We check
    to see that it is logged.

    Note that both of these scenarios are common occurances. The purpose of this test is
    to ensure that they are logged.
    
    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """
    cluster = cluster_maker(3)
    config = cluster.build_cluster_config()
    cluster.set_configs(config)
    uri_1 = cluster.node_uris[0]
    uri_2 = cluster.node_uris[1]
    uri_3 = cluster.node_uris[2]

    ts_1 = cluster.nodes[uri_1]
    ts_2 = cluster.nodes[uri_2]
    ts_3 = cluster.nodes[uri_3]

    cluster.test_trace.start_subtest("Initial election, normal",
                                     test_path_str=str('/'.join(Path(__file__).parts[-2:])),
                                     test_doc_string=test_restart_during_heartbeat.__doc__)
    await cluster.start()
    await ts_3.start_campaign()
    sequence = SNormalElection(cluster, 1)
    await cluster.run_sequence(sequence)

    assert ts_3.get_role_name() == "LEADER"
    assert ts_1.get_leader_uri() == uri_3
    assert ts_2.get_leader_uri() == uri_3

    # Get the leader to send out heartbeats, but
    # don't allow followers to get them yet, then
    # demote leader and let the messages fly.
    # The leader, now a follower should get a couple
    # of reply messages that it doesn't expect, and
    # should show up in hull log
    cluster.test_trace.start_subtest("Node 3 is leader, getting it to sent heartbeats but not allowing delivery, then demoting leader")
    ts_3.get_message_problem_history(clear=True)
    await ts_3.send_heartbeats()
    await cluster.deliver_all_pending(out_only=True)
    assert len(ts_1.in_messages) == 1
    assert len(ts_2.in_messages) == 1
    logger.debug("about to demote %s %s", uri_3, ts_3.get_role())
    await ts_3.do_demote_and_handle()
    cluster.test_trace.start_subtest("Node 3 is demoted, now delivering pending messages and checking that the replies are reported as issuesw")
    await cluster.deliver_all_pending()
    hist = ts_3.get_message_problem_history()
    assert len(hist) == 2

    cluster.test_trace.start_subtest("Node 3 starting a new election")
    await ts_3.start_campaign()
    sequence = SNormalElection(cluster, 1)
    await cluster.run_sequence(sequence)
    assert ts_3.get_role_name() == "LEADER"
    assert ts_1.get_leader_uri() == uri_3
    assert ts_2.get_leader_uri() == uri_3
    # now just poke a random message in there to get
    # at the code that is very hard to arrange by
    # tweaking roles, a vote response that isn't expected
    # when the receiver is not a newly elected leader,
    # with leftover votes coming in.
    
    cluster.test_trace.start_subtest("Generating extra vote repsonse message for Node 3 and checking that it is reported")
    msg = RequestVoteResponseMessage(sender=uri_2, receiver=uri_3,
                                     term=0, prevLogIndex=0, prevLogTerm=0, vote=False)
    ts_3.in_messages.append(msg)
    ts_3.get_message_problem_history(clear=True)
    await ts_3.do_next_in_msg()
    hist = ts_3.get_message_problem_history(clear=True)
    assert len(hist) == 1
    rep = hist[0]
    assert json.dumps(rep['message'], default=lambda o:o.__dict__) == json.dumps(msg, default=lambda o:o.__dict__)

async def test_slow_voter(cluster_maker):
    """
    This tests the rare case where a candidate starts a new election, sends requests, then for some
    reason starts another election at a higher term and then receives a vote reponse from the previous term.
    This seems pretty unlikely in practice, but not impossible, so there is code for it. About three lines.
    All this test does is poke those lines.

    It goes like this:

    1. Normal election
    2. The leader (node 3) is forced to start a new election.
    3. Messages are managed such that the followers get the requests for vote and send replies,
       but everything stops before the candidate gets their responses.
    4. The candidate starts a new election, so term is now 3
    5. The messages are processed enough to see that the candidate gets the stale once, and
       then the new voting cycle works and yes votes for the new term arrive.
    6. The rest of the messages are delivered to complete the election
    
    
    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """
    cluster = cluster_maker(3)
    config = cluster.build_cluster_config()
    cluster.set_configs(config)
    uri_1 = cluster.node_uris[0]
    uri_2 = cluster.node_uris[1]
    uri_3 = cluster.node_uris[2]

    ts_1 = cluster.nodes[uri_1]
    ts_2 = cluster.nodes[uri_2]
    ts_3 = cluster.nodes[uri_3]

    cluster.test_trace.start_subtest("Initial election, normal",
                                     test_path_str=str('/'.join(Path(__file__).parts[-2:])),
                                     test_doc_string=test_slow_voter.__doc__)
    await cluster.start()
    await ts_3.start_campaign()
    sequence = SNormalElection(cluster, 1)
    await cluster.run_sequence(sequence)
    
    assert ts_3.get_role_name() == "LEADER"
    assert ts_1.get_leader_uri() == uri_3
    assert ts_2.get_leader_uri() == uri_3

    # Now get an re-election started on current leader,
    # but block the follower's votes, then trigger the
    # candidate to retry, which will up the term, then let
    # the old votes flow in. They should get ignored
    # and the election should succeed
    cluster.test_trace.start_subtest("Node 3 is leader, demoting and ensuring vote requests are delivered, but responses not accepted yet")
    await ts_3.do_demote_and_handle(None)
    await ts_3.do_leader_lost()
    await ts_3.do_next_out_msg()
    await ts_3.do_next_out_msg()
    msg = await ts_1.do_next_in_msg()
    assert msg is not None
    msg = await ts_2.do_next_in_msg()
    assert msg is not None
    assert len(ts_1.out_messages) == 1
    assert len(ts_2.out_messages) == 1
    old_term = await ts_3.log.get_term()
    cluster.test_trace.start_subtest("Starting another election at node 3, whose term is now 3 and checking that pending messages are stale")
    await ts_3.start_campaign()
    assert old_term + 1 == await ts_3.log.get_term()
    # this should be a stale vote
    msg = await ts_1.do_next_out_msg()
    msg = await ts_3.do_next_in_msg()
    assert msg.term == old_term
    # this too
    msg = await ts_2.do_next_out_msg()
    msg = await ts_3.do_next_in_msg()
    assert msg.term == old_term
    logger.debug("--------------------Stale votes processed")
    # stale votes should be ignored, election should complete normally

    # so we need two more outs from the candidate ts_3
    # two more ins for the followers
    # then two outs from them to get their new votes
    # then two ins to candiate and the first one should
    # settle the election
    cluster.test_trace.start_subtest("Allowing some messages for second election, checking that term is correct")
    new_term = await ts_3.log.get_term()
    await ts_3.do_next_out_msg()
    await ts_3.do_next_out_msg()
    await ts_2.do_next_in_msg()
    msg = await ts_2.do_next_out_msg()
    assert msg.term == new_term
    assert msg.vote == True
    await ts_1.do_next_in_msg()
    msg = await ts_1.do_next_out_msg()
    assert msg.term == new_term
    assert msg.vote == True
    cluster.test_trace.start_subtest("Allowing remainging messages for normal election to complete")
    await cluster.deliver_all_pending()
    assert ts_3.get_role_name() == "LEADER"
    assert ts_1.get_leader_uri() == uri_3
    assert ts_2.get_leader_uri() == uri_3


async def test_message_errors(cluster_maker):
    """
    This test uses error insertion to make things that normally don't blow up do so. Code that
    gets run a million times with no problem, but that has the potential to blow up if something
    funky like memory corruption happens. We have code to catch these cases, so there needs
    to be code to test that the catches work.

    Starts with a normal election, then inserts two errors into the message processing code.
    
    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """
    cluster = cluster_maker(3)
    config = cluster.build_cluster_config()
    cluster.set_configs(config)
    uri_1 = cluster.node_uris[0]
    uri_2 = cluster.node_uris[1]
    uri_3 = cluster.node_uris[2]

    ts_1 = cluster.nodes[uri_1]
    ts_2 = cluster.nodes[uri_2]
    ts_3 = cluster.nodes[uri_3]

    cluster.test_trace.start_subtest("Initial election, normal, then a couple of message processing error are inserted",
                                     test_path_str=str('/'.join(Path(__file__).parts[-2:])),
                                     test_doc_string=test_message_errors.__doc__)
    await cluster.start()
    await ts_3.start_campaign()
    sequence = SNormalElection(cluster, 1)
    await cluster.run_sequence(sequence)
    assert ts_3.get_role_name() == "LEADER"
    assert ts_1.get_leader_uri() == uri_3
    assert ts_2.get_leader_uri() == uri_3
    
    ts_1.hull.explode_on_message_code = AppendEntriesMessage.get_code()
    
    hist = ts_1.get_message_problem_history(clear=True)
    await ts_3.send_heartbeats()
    await ts_3.do_next_out_msg()
    await ts_3.do_next_out_msg()
    await ts_1.do_next_in_msg()
    
    hist = ts_1.get_message_problem_history(clear=True)
    assert len(hist) == 1
    
    ts_1.hull.explode_on_message_code = None

    ts_1.hull.corrupt_message_with_code = AppendEntriesMessage.get_code()
    await ts_3.send_heartbeats()
    await ts_3.do_next_out_msg()
    await ts_3.do_next_out_msg()
    await ts_1.do_next_in_msg()
    hist = ts_1.get_message_problem_history(clear=True)
    assert len(hist) == 1
    
