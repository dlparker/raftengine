#!/usr/bin/env python
import asyncio
import logging
import pytest
import time
from raftengine.messages.request_vote import RequestVoteMessage,RequestVoteResponseMessage
from raftengine.messages.append_entries import AppendEntriesMessage, AppendResponseMessage


from dev_tools.servers import WhenElectionDone
from dev_tools.servers import PausingCluster, cluster_maker
from dev_tools.servers import setup_logging
from dev_tools.servers import SNormalElection

#extra_logging = [dict(name=__name__, level="debug"),]
#setup_logging(extra_logging)
setup_logging()
logger = logging.getLogger("test_code")


async def test_heartbeat_1(cluster_maker):
    cluster = cluster_maker(3)
    heartbeat_period = 0.01
    config = cluster.build_cluster_config(heartbeat_period=heartbeat_period)
    cluster.set_configs(config)
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]

    await cluster.start(timers_disabled=False)
    await ts_3.hull.start_campaign()

    sequence = SNormalElection(cluster, 1)
    await cluster.run_sequence(sequence)
    assert ts_3.hull.get_state_code() == "LEADER"
    assert ts_1.hull.state.leader_uri == uri_3
    assert ts_2.hull.state.leader_uri == uri_3

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

async def test_heartbeat_2(cluster_maker):
    cluster = cluster_maker(3)
    heartbeat_period = 0.02
    election_timeout_min = 0.2
    election_timeout_max = 0.5
    config = cluster.build_cluster_config(heartbeat_period=heartbeat_period,
                                          election_timeout_min=election_timeout_min, 
                                          election_timeout_max=election_timeout_max)
                                          
    cluster.set_configs(config)
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]

    await cluster.start(timers_disabled=False)
    await ts_3.hull.start_campaign()

    sequence = SNormalElection(cluster, 1)
    await cluster.run_sequence(sequence)
    await cluster.start_auto_comms()
    assert ts_3.hull.get_state_code() == "LEADER"
    assert ts_1.hull.state.leader_uri == uri_3
    assert ts_2.hull.state.leader_uri == uri_3
    # make sure running for a time exceeding the timeout does not
    # cause a leader lost situation
    fraction = election_timeout_max/5.0
    start_time = time.time()
    while time.time() - start_time < election_timeout_max * 2:
        await asyncio.sleep(fraction)

    assert ts_3.hull.get_state_code() == "LEADER"
    assert ts_1.hull.state.leader_uri == uri_3
    assert ts_2.hull.state.leader_uri == uri_3
    await cluster.stop_auto_comms()
        
async def test_lost_leader_1(cluster_maker):
    cluster = cluster_maker(3)
    # make leader too slow, will cause re-election
    heartbeat_period = 0.2
    election_timeout_min = 0.02
    election_timeout_max = 0.05
    config = cluster.build_cluster_config(heartbeat_period=heartbeat_period,
                                          election_timeout_min=election_timeout_min, 
                                          election_timeout_max=election_timeout_max)
    cluster.set_configs(config)
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]

    await cluster.start(timers_disabled=False)
    await ts_3.hull.start_campaign()
    await cluster.deliver_all_pending()
    await cluster.run_election()
    await cluster.deliver_all_pending()
    assert ts_3.hull.get_state_code() == "LEADER"
    assert ts_1.hull.state.leader_uri == uri_3
    assert ts_2.hull.state.leader_uri == uri_3
    await ts_3.hull.demote_and_handle(None)
    
    # Test that election happens in appoximately the leader_lost timeout
    start_time = time.time()
    fraction = election_timeout_max/10.0
    while time.time() - start_time < election_timeout_max * 2:
        await cluster.deliver_all_pending()
        if (ts_1.hull.state.state_code == "LEADER"
            or ts_2.hull.state.state_code == "LEADER"
            or ts_3.hull.state.state_code == "LEADER"):
            break
        await asyncio.sleep(fraction)
    assert (ts_1.hull.state.state_code == "LEADER"
            or ts_2.hull.state.state_code == "LEADER"
            or ts_3.hull.state.state_code == "LEADER")

    for ts in ts_1, ts_2, ts_3:
        if ts.hull.state.state_code == "LEADER":
            leader = ts
            leader_uri = ts.uri
            break
    assert await leader.log.get_term() > 1
    
async def test_election_timeout_1(cluster_maker):
    cluster = cluster_maker(3)
    heartbeat_period = 0.001
    election_timeout_min = 0.009
    election_timeout_max = 0.011
    config = cluster.build_cluster_config(heartbeat_period=heartbeat_period,
                                          election_timeout_min=election_timeout_min, 
                                          election_timeout_max=election_timeout_max)
    cluster.set_configs(config)
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]

    await cluster.start(timers_disabled=True)
    await ts_1.hull.start_campaign()
    sequence = SNormalElection(cluster, 1)
    await cluster.run_sequence(sequence)

    assert ts_1.hull.get_state_code() == "LEADER"
    assert ts_2.hull.state.leader_uri == uri_1
    assert ts_2.hull.state.leader_uri == uri_1

    # Now arrange another election and make sure that the candidate
    # experiences a timeout, no votes in required time. It should
    # incr the term and retry so we can monitor by term value
    orig_term = await ts_2.log.get_term()
    ts_1.block_network()
    ts_3.block_network()
    await ts_1.hull.demote_and_handle(None)
    await cluster.start_auto_comms()
    await ts_2.enable_timers()
    start_time = time.time()
    fraction = election_timeout_max/50.0
    while (time.time() - start_time < election_timeout_max  * 2
           and await ts_2.log.get_term() == orig_term):
        await asyncio.sleep(fraction)
    term_now = await ts_2.log.get_term()
    assert term_now != orig_term
    if term_now == orig_term + 1:
        # not done yet, just running as candidate for first time,
        start_time = time.time()
        while (time.time() - start_time < election_timeout_max  * 2
               and await ts_2.log.get_term() == term_now):
            await asyncio.sleep(fraction)
    final_term = await ts_2.log.get_term()
    assert final_term == orig_term + 2

    ts_1.unblock_network()
    ts_3.unblock_network()
    # now make sure it can win
    start_time = time.time()
    while (time.time() - start_time < election_timeout_max  * 2
           and ts_2.hull.state.state_code != "LEADER"):
            await asyncio.sleep(fraction)
    assert ts_2.hull.state.state_code == "LEADER"
    
    await cluster.stop_auto_comms()
