#!/usr/bin/env python
import asyncio
import logging
import pytest
import time
import json
from raftengine.messages.request_vote import RequestVoteMessage,RequestVoteResponseMessage
from raftengine.messages.append_entries import AppendEntriesMessage, AppendResponseMessage

from dev_tools.servers import WhenElectionDone
from dev_tools.servers import PausingCluster, cluster_maker
from dev_tools.servers import setup_logging

#extra_logging = [dict(name=__name__, level="debug"),]
#setup_logging(extra_logging)
setup_logging()
logger = logging.getLogger("test_code")

async def test_restart_during_heartbeat(cluster_maker):
    cluster = cluster_maker(3)
    config = cluster.build_cluster_config()
    cluster.set_configs(config)
    uri_1 = cluster.node_uris[0]
    uri_2 = cluster.node_uris[1]
    uri_3 = cluster.node_uris[2]

    ts_1 = cluster.nodes[uri_1]
    ts_2 = cluster.nodes[uri_2]
    ts_3 = cluster.nodes[uri_3]

    await cluster.start()
    await ts_3.start_campaign()
    ts_1.set_trigger(WhenElectionDone())
    ts_2.set_trigger(WhenElectionDone())
    ts_3.set_trigger(WhenElectionDone())
        
    await asyncio.gather(ts_1.run_till_triggers(),
                         ts_2.run_till_triggers(),
                         ts_3.run_till_triggers())
    
    ts_1.clear_triggers()
    ts_2.clear_triggers()
    ts_3.clear_triggers()
    assert ts_3.get_role_name() == "LEADER"
    assert ts_1.get_leader_uri() == uri_3
    assert ts_2.get_leader_uri() == uri_3

    # Get the leader to send out heartbeats, but
    # don't allow receives to get them yet, then
    # demote leader and let the messages fly.
    # The leader, now a follower should get a couple
    # of reply messages that it doesn't expect, and
    # should show up in hull log
    ts_3.get_message_problem_history(clear=True)
    await ts_3.send_heartbeats()
    await cluster.deliver_all_pending(out_only=True)
    assert len(ts_1.in_messages) == 1
    assert len(ts_2.in_messages) == 1
    logger.debug("about to demote %s %s", uri_3, ts_3.get_role())
    await ts_3.do_demote_and_handle()
    await cluster.deliver_all_pending()
    hist = ts_3.get_message_problem_history()
    assert len(hist) == 2

    await ts_3.start_campaign()
    ts_1.set_trigger(WhenElectionDone())
    ts_2.set_trigger(WhenElectionDone())
    ts_3.set_trigger(WhenElectionDone())
        
    await asyncio.gather(ts_1.run_till_triggers(),
                         ts_2.run_till_triggers(),
                         ts_3.run_till_triggers())
    
    ts_1.clear_triggers()
    ts_2.clear_triggers()
    ts_3.clear_triggers()
    assert ts_3.get_role_name() == "LEADER"
    assert ts_1.get_leader_uri() == uri_3
    assert ts_2.get_leader_uri() == uri_3
    # now just poke a random message in there to get
    # at the code that is very hard to arrange by
    # tweaking roles, a vote response that isn't expected
    # when the receiver is not a newly elected leader,
    # with leftover votes coming in.
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
    cluster = cluster_maker(3)
    config = cluster.build_cluster_config()
    cluster.set_configs(config)
    uri_1 = cluster.node_uris[0]
    uri_2 = cluster.node_uris[1]
    uri_3 = cluster.node_uris[2]

    ts_1 = cluster.nodes[uri_1]
    ts_2 = cluster.nodes[uri_2]
    ts_3 = cluster.nodes[uri_3]

    await cluster.start()
    await ts_3.start_campaign()
    ts_1.set_trigger(WhenElectionDone())
    ts_2.set_trigger(WhenElectionDone())
    ts_3.set_trigger(WhenElectionDone())
        
    await asyncio.gather(ts_1.run_till_triggers(),
                         ts_2.run_till_triggers(),
                         ts_3.run_till_triggers())
    
    ts_1.clear_triggers()
    ts_2.clear_triggers()
    ts_3.clear_triggers()
    assert ts_3.get_role_name() == "LEADER"
    assert ts_1.get_leader_uri() == uri_3
    assert ts_2.get_leader_uri() == uri_3

    # Now get an re-election started on current leader,
    # but block the follower's votes, then trigger the
    # candidate to retry, which will up the term, then let
    # the old votes flow in. They should get ignored
    # and the election should succeed
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
    new_term = await ts_3.log.get_term()
    msg = await ts_3.do_next_out_msg()
    assert msg.term == new_term
    msg = await ts_3.do_next_out_msg()
    assert msg.term == new_term
    msg = await ts_1.do_next_in_msg()
    assert msg.term == new_term
    msg = await ts_2.do_next_in_msg()
    assert msg.term == new_term
    msg = await ts_1.do_next_out_msg()
    assert msg.term == new_term
    assert msg.vote == True
    msg = await ts_2.do_next_out_msg()
    assert msg.term == new_term
    assert msg.vote == True
    msg = await ts_3.do_next_in_msg()
    assert msg.term == new_term
    assert msg.vote == True
    assert ts_3.get_role_name() == "LEADER"
    msg = await ts_3.do_next_in_msg()
    assert msg.term == new_term
    assert msg.vote == True
    assert ts_1.get_leader_uri() == uri_3
    assert ts_2.get_leader_uri() == uri_3


async def test_message_errors(cluster_maker):
    cluster = cluster_maker(3)
    config = cluster.build_cluster_config()
    cluster.set_configs(config)
    uri_1 = cluster.node_uris[0]
    uri_2 = cluster.node_uris[1]
    uri_3 = cluster.node_uris[2]

    ts_1 = cluster.nodes[uri_1]
    ts_2 = cluster.nodes[uri_2]
    ts_3 = cluster.nodes[uri_3]

    await cluster.start()
    await ts_3.start_campaign()
    ts_1.set_trigger(WhenElectionDone())
    ts_2.set_trigger(WhenElectionDone())
    ts_3.set_trigger(WhenElectionDone())
        
    await asyncio.gather(ts_1.run_till_triggers(),
                         ts_2.run_till_triggers(),
                         ts_3.run_till_triggers())
    
    ts_1.clear_triggers()
    ts_2.clear_triggers()
    ts_3.clear_triggers()
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
    
