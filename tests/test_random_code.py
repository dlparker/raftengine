#!/usr/bin/env python
import asyncio
import logging
import pytest
import time
from raftengine.messages.request_vote import RequestVoteMessage,RequestVoteResponseMessage
from raftengine.messages.append_entries import AppendEntriesMessage, AppendResponseMessage
from servers import SNormalElection
from servers import setup_logging

extra_logging = [dict(name=__name__, level="debug"),]
setup_logging(extra_logging)

from servers import WhenElectionDone
from servers import PausingCluster, cluster_maker

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



