#!/usr/bin/env python
import asyncio
import logging
import pytest
import time
from pathlib import Path
from raftengine.messages.request_vote import RequestVoteMessage,RequestVoteResponseMessage
from raftengine.messages.append_entries import AppendEntriesMessage, AppendResponseMessage
from dev_tools.servers import SNormalElection, SNormalCommand
from dev_tools.servers import setup_logging
from dev_tools.servers import WhenElectionDone
from dev_tools.servers import PausingCluster, cluster_maker

extra_logging = [dict(name=__name__, level="debug"),]
setup_logging(extra_logging)


# Stuff in here is just things that help me develop tests by writing
# explority code that runs in the test context, just to figure out
# what will work before adding it to real code.
# I might keep old code around for a while by renaming the test so
# it won't be gathered, then remove it when I am sure there is no
# more need for it.


async def test_normal_election_sequence_1(cluster_maker):
    cluster = cluster_maker(3)
    cluster.set_configs()
    await cluster.start()
    
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]

    await ts_1.hull.start_campaign()
    
    sequence = SNormalElection(cluster, 1)
    await cluster.run_sequence(sequence)

    assert ts_1.hull.get_state_code() == "LEADER"
    assert ts_2.hull.state.leader_uri == uri_1
    assert ts_3.hull.state.leader_uri == uri_1


async def test_normal_election_sequence_2(cluster_maker):
    cluster = cluster_maker(5)
    cluster.set_configs()
    await cluster.start()
    
    uri_1, uri_2, uri_3, uri_4, uri_5 = cluster.node_uris
    ts_1, ts_2, ts_3, ts_4, ts_5 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3, uri_4, uri_5]]

    await ts_1.hull.start_campaign()
    
    sequence = SNormalElection(cluster, 1)
    await cluster.run_sequence(sequence)

    assert ts_1.hull.get_state_code() == "LEADER"
    assert ts_2.hull.state.leader_uri == uri_1
    assert ts_3.hull.state.leader_uri == uri_1
    assert ts_4.hull.state.leader_uri == uri_1
    assert ts_5.hull.state.leader_uri == uri_1

async def test_normal_command_sequence_1(cluster_maker):
    cluster = cluster_maker(3)
    cluster.set_configs()
    await cluster.start()
    
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]

    await ts_1.hull.start_campaign()
    
    sequence1 = SNormalElection(cluster, 1)
    await cluster.run_sequence(sequence1)

    assert ts_1.hull.get_state_code() == "LEADER"
    assert ts_2.hull.state.leader_uri == uri_1
    assert ts_3.hull.state.leader_uri == uri_1

    sequence2 = SNormalCommand(cluster, "add 1", 1)
    result = await cluster.run_sequence(sequence2)

    assert result.result == 1
    assert ts_1.operations.total == 1
    assert ts_2.operations.total == 1
    assert ts_3.operations.total == 1

    sequence3 = SNormalCommand(cluster, "add 1", 1)
    result = await cluster.run_sequence(sequence3)

    assert result.result == 2
    assert ts_1.operations.total == 2
    assert ts_2.operations.total == 2
    assert ts_3.operations.total == 2


        
