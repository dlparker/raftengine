#!/usr/bin/env python
import asyncio
import logging
import time
import json
import random
from pathlib import Path
from pprint import pprint
import pytest
from raftengine.api.types import ClusterConfig, NodeRec, ClusterSettings
from raftengine.api.log_api import LogRec, RecordCode, LogAPI
from raftengine.api.pilot_api import PilotAPI
from raftengine.api.hull_config import ClusterInitConfig
from dev_tools.memory_log import MemoryLog
from dev_tools.sequences import SNormalElection, SNormalCommand, SPartialElection, SPartialCommand
from dev_tools.logging_ops import setup_logging
from dev_tools.pausing_cluster import PausingCluster, cluster_maker
from dev_tools.operations import DictTotalsOps, SnapShot

#extra_logging = [dict(name=__name__, level="debug"),]
#setup_logging(extra_logging)
default_level='error'
default_level='debug'
setup_logging(default_level=default_level)
logger = logging.getLogger("test_code")


# Stuff in here is just things that help me develop tests by writing
# explority code that runs in the test context, just to figure out
# what will work before adding it to real code.
# I might keep old code around for a while by renaming the test so
# it won't be gathered, then remove it when I am sure there is no
# more need for it.
async def test_dict_ops():

    class FakeServer:

        def __init__(self):
            self.log = MemoryLog()
            self.ops = DictTotalsOps(self)

        async def process_command(self, command, serial):
            last_index = await self.log.get_last_index()
            rec = LogRec(index=last_index + 1, term=1, command=command, committed=True, applied=True)
            await self.log.append(rec)
            await self.ops.process_command(command, serial)

    fs1 = FakeServer()
    ops1 = fs1.ops
    
    for i in range(1, 11):
        command = f'add {i} {random.randint(1,100)}'
        await fs1.process_command(command, i)
    assert len(ops1.totals) == 10
    tool_1 = ops1.snapshot_tool
    ss1 = await tool_1.take_snapshot()
    assert len(ss1.tool.data) == 10

    fs2 = FakeServer()
    ops2 = fs2.ops
    # this is what a pilot should do on a call to begin_snapshot_import
    ss2 = SnapShot(ss1.last_index, ss1.last_term, ops2.snapshot_tool)
    
    offset = 0
    done = False
    while not done:
        chunk, new_offset, done = await ss1.tool.get_snapshot_chunk(ss2, offset)
        await ss2.tool.load_snapshot_chunk(ss2, chunk)
        offset = new_offset
    for key in ops1.totals:
        assert ops1.totals[key] == ops2.totals[key]
    
async def test_snapshot_1(cluster_maker):

    cluster = cluster_maker(3)
    tconfig = cluster.build_cluster_config()
    cluster.set_configs(use_ops=DictTotalsOps)

    await cluster.start()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]

    for i in range(10):
        for x in range(1, 10):
            command = f'add {x} {random.randint(1,100)}'
            for ts in [ts_1, ts_2, ts_3]:
                await ts.fake_command2(command)
                
    last_index = await ts_1.log.get_last_index()
    last_term = await ts_1.log.get_last_term()
    rec = await ts_1.log.read(last_index)
    ts_1_ss = await ts_1.take_snapshot()

    # log should now be empty
    assert await ts_1.log.read(last_index) is None
    assert await ts_1.log.get_first_index() is None
    assert await ts_1.log.read(last_index + 1) is None
    assert await ts_1.log.get_last_index() == ts_1_ss.last_index
    assert await ts_1.log.get_last_term() == 1

    ts_4 = await cluster.add_node()
    ts_4_ss = await ts_4.begin_snapshot_import(ts_1_ss.last_index, ts_1_ss.last_term)
    tool_4 = ts_4_ss.tool
    offset = 0
    done = False
    while not done:
        chunk, new_offset, done = await ts_1_ss.tool.get_snapshot_chunk(ts_1_ss, offset)
        await tool_4.load_snapshot_chunk(ts_4_ss, chunk)
        offset = new_offset
    await tool_4.apply_snapshot()
    assert ts_4.operations.totals == ts_1.operations.totals
    assert await ts_4.log.get_first_index() == None
    assert await ts_4.log.get_last_index() == await ts_1.log.get_last_index()
    assert ts_4.operations.totals == ts_1.operations.totals
        
async def test_snapshot_2(cluster_maker):
    """
    Test the simplest snapshot process, at a follower in a quiet cluster. After
    it is installed, have that node become the leader and make sure new commands
    work.

    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    
    """
    cluster = cluster_maker(3)
    config = cluster.build_cluster_config(use_pre_vote=False)
    cluster.set_configs(config, use_ops=DictTotalsOps)

    cluster.test_trace.start_subtest("Starting election at node 1 of 3",
                                     test_path_str=str('/'.join(Path(__file__).parts[-2:])),
                                     test_doc_string=test_snapshot_2.__doc__)
    await cluster.start()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]
    
    await ts_1.start_campaign()
    await cluster.run_election()
    cluster.test_trace.start_subtest("Node 1 is leader, runing commands by direct fake path")

    # The operations object maintains a dictionary of totals,
    # so "add x 1" adds one to the "x" dictionary entry.
    # We're going to use numbers as keys, and add a random value to
    # each key, 10 times.
    for i in range(10):
        for x in range(1, 10):
            command = f'add {x} {random.randint(1,100)}'
            for ts in [ts_1, ts_2, ts_3]:
                await ts.fake_command2(command)
                
    last_index = await ts_2.log.get_last_index()
    last_term = await ts_2.log.get_last_term()
    rec = await ts_2.log.read(last_index)
    ts_2_ss = await ts_2.take_snapshot()

    # log should now be empty
    assert await ts_2.log.read(last_index) is None
    assert await ts_2.log.get_first_index() is None
    assert await ts_2.log.read(last_index + 1) is None
    assert await ts_2.log.get_last_index() == ts_2_ss.last_index
    assert await ts_2.log.get_last_term() == 1

    cluster.test_trace.start_subtest("Node 2 has snapshot and empty log, switching it to leader")
        
    await ts_1.do_demote_and_handle()
    await ts_2.start_campaign(authorized=True)
    await cluster.run_election()
    assert ts_2.hull.is_leader()
    assert ts_1.hull.is_leader() is False
    assert await ts_2.log.get_last_term() == 2
    assert await ts_2.log.get_first_index() == ts_2_ss.last_index + 1
    assert await ts_2.log.get_last_index() == ts_2_ss.last_index + 1
    term_start_rec = await ts_2.log.read()
    assert term_start_rec is not None
    assert term_start_rec.index == last_index + 1
    assert term_start_rec.term == 2
    assert await ts_2.log.get_last_index() == last_index + 1

    command_result = await cluster.run_command("add 1 1", 1)
    assert await ts_2.log.get_first_index() == ts_2_ss.last_index + 1
    assert await ts_2.log.get_last_index() == ts_2_ss.last_index + 2
        
async def test_snapshot_3(cluster_maker):
    """
    Test the snapshot process when the leader is told to snapshot. It should
    transfer power and then do the snapshot, then rejoin cluster.

    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """
    cluster = cluster_maker(3)
    config = cluster.build_cluster_config(use_pre_vote=False)
    cluster.set_configs(config, use_ops=DictTotalsOps)

    cluster.test_trace.start_subtest("Starting election at node 1 of 3",
                                     test_path_str=str('/'.join(Path(__file__).parts[-2:])),
                                     test_doc_string=test_snapshot_2.__doc__)
    await cluster.start()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]
    
    await ts_1.start_campaign()
    await cluster.run_election()
    cluster.test_trace.start_subtest("Node 1 is leader, runing commands by direct fake path")

    # The operations object maintains a dictionary of totals,
    # so "add x 1" adds one to the "x" dictionary entry.
    # We're going to use numbers as keys, and add a random value to
    # each key, 10 times.
    for i in range(10):
        for x in range(1, 10):
            command = f'add {x} {random.randint(1,100)}'
            for ts in [ts_1, ts_2, ts_3]:
                await ts.fake_command2(command)
                
    last_index = await ts_1.log.get_last_index()
    last_term = await ts_1.log.get_last_term()
    rec = await ts_1.log.read(last_index)
    cluster.test_trace.start_subtest("Telling leader node (node 1) to snapshot but blocking net, should fail because it can't transfer power")
    with pytest.raises(Exception):
        ts_1_ss = await ts_1.take_snapshot(timeout=0.05)
    cluster.test_trace.start_subtest("Telling leader node (node 1) to snapshot, should make it transfer power")
    await cluster.start_auto_comms()
    ts_1_ss = await ts_1.take_snapshot()
    await cluster.stop_auto_comms()
    assert ts_1.hull.is_leader() is False
    new_leader = cluster.get_leader()
    assert new_leader is not None
    assert new_leader.uri != ts_1.uri
    
    # log should now have only the term start record
    assert await ts_1.log.read(last_index) is None
    assert await ts_1.log.get_first_index() == last_index + 1
    assert await ts_1.log.get_last_index() == ts_1_ss.last_index + 1
    assert await ts_1.log.read(last_index + 1) is not None
    assert await ts_1.log.get_last_term() == 2

    assert await new_leader.log.read(last_index) is not None
    assert await new_leader.log.get_first_index() is not None
    assert await new_leader.log.read(last_index + 1) is not None
    assert await new_leader.log.get_last_index() == ts_1_ss.last_index + 1
    assert await new_leader.log.get_last_term() == 2

    cluster.test_trace.start_subtest("Node 1 has snapshot and empty log, {new_leader.uri} is leader, running command")
        
    command_result = await cluster.run_command("add 1 1", 1)
    assert await ts_1.log.get_first_index() == ts_1_ss.last_index + 1
    assert await ts_1.log.get_last_index() == ts_1_ss.last_index + 2
        
