#!/usr/bin/env python
import asyncio
import logging
import pytest
import time
from pathlib import Path
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



async def test_pending_record_changes():
    from dev_tools.sqlite_log import SqliteLog
    from dev_tools.memory_log import MemoryLog
    from raftengine.log.log_api import LogRec
    m_log = MemoryLog()

    path = Path('/tmp', "test_log.sqlite")
    if path.exists():
        path.unlink()
    s_log = SqliteLog(path)
    s_log.start()

    for log in [m_log, s_log]:
        no_rec = await log.get_pending()
        assert no_rec is None
        p_rec = LogRec(term=1, user_data="foo")
        with pytest.raises(Exception):
            await log.save_pending(p_rec)
        p_rec.index = 1
        await log.save_pending(p_rec)
        x_rec = await log.get_pending()
        assert x_rec is not None
        assert x_rec.index == 1
        assert x_rec.term == 1
        assert x_rec.user_data == "foo"
        next_rec = LogRec(term=1, user_data="bar")
        next_rec.index = 1
        # correct index, but we already got one
        with pytest.raises(Exception):
            await log.save_pending(next_rec)
        await log.commit_pending(p_rec)
        assert await log.read() is not None
        # should work now
        next_rec.index = 2
        await log.save_pending(next_rec)
        await log.clear_pending()
        z_rec = await log.get_pending()
        assert z_rec is None
