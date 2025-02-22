#!/usr/bin/env python
import asyncio
import logging
import pytest
import time
from pathlib import Path
from raftengine.messages.request_vote import RequestVoteMessage,RequestVoteResponseMessage
from raftengine.messages.append_entries import AppendEntriesMessage, AppendResponseMessage
from servers import SNormalElection, SNormalCommand
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


async def test_log_stuff():
    from raftengine.api.log_api import LogRec,RecordCode, CommandLogRec, ConfigLogRec
    import json
    from raftengine.messages.append_entries import AppendEntriesMessage
    from dev_tools.memory_log import MemoryLog
    from dev_tools.sqlite_log import SqliteLog
    from raftengine.api.log_api import LogRec
    m_log = MemoryLog()

    path = Path('/tmp', "test_log.sqlite")
    if path.exists():
        path.unlink()
    s_log = SqliteLog(path)
    s_log.start()

    rec1 = LogRec(term=1, command="add 1")
    rec2 = LogRec(term=1, command="add 2")
    msg = AppendEntriesMessage('1', '2', '1', 0, 0, [rec1, rec2], 2)

    # 

    for log in [m_log, s_log]:

        [rec_1, rec_2] = await log.append_multi([rec1, rec2])
        assert await log.get_last_index() == 2
        assert await log.get_last_term() == 1
        assert rec_1.index == 1
        assert rec_1.command == 'add 1'
        assert not rec_1.committed
        assert rec_2.index == 2
        assert rec_2.command == 'add 2'
        
        rec_2b = await log.read(await log.get_last_index())
        assert rec_2b.index == 2
        assert rec_2b.command == 'add 2'
        
        rec_1.committed = True
        await log.replace(rec_1)
        loc_c = await log.get_commit_index()
        assert loc_c == 1
        await log.update_and_commit(rec_2)
        loc_c = await log.get_commit_index()
        assert loc_c == 2
    
        
