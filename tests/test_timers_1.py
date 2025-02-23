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

extra_logging = [dict(name=__name__, level="debug"),]
setup_logging(extra_logging)


async def test_heartbeat_1(cluster_maker):
    cluster = cluster_maker(3)
    heartbeat_period = 0.01
    config = cluster.build_cluster_config(heartbeat_period=heartbeat_period)
    cluster.set_configs(config)
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]

    logger = logging.getLogger(__name__)
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

    logger = logging.getLogger(__name__)
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
    heartbeat_period = 0.1
    election_timeout_min = 0.02
    election_timeout_max = 0.05
    config = cluster.build_cluster_config(heartbeat_period=heartbeat_period,
                                          election_timeout_min=election_timeout_min, 
                                          election_timeout_max=election_timeout_max)
    cluster.set_configs(config)
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]

    logger = logging.getLogger(__name__)
    await cluster.start(timers_disabled=False)
    await ts_3.hull.start_campaign()
    sequence = SNormalElection(cluster, 1)
    await cluster.run_sequence(sequence)

    assert ts_3.hull.get_state_code() == "LEADER"
    assert ts_1.hull.state.leader_uri == uri_3
    assert ts_2.hull.state.leader_uri == uri_3

    # Test that election happens in appoximately the leader_lost timeout
    start_time = time.time()
    fraction = election_timeout_max/10.0
    while time.time() - start_time < election_timeout_max  + (fraction * 2):
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
    
