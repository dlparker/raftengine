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
from dev_tools.sqlite_log import SqliteLog
from dev_tools.sequences import SNormalElection, SNormalCommand, SPartialElection, SPartialCommand
from dev_tools.logging_ops import setup_logging
from dev_tools.pausing_cluster import PausingCluster, cluster_maker
from dev_tools.pausing_server import setup_sqlite_log
from dev_tools.operations import DictTotalsOps, SnapShot
from raftengine.messages.snapshot import SnapShotMessage, SnapShotResponseMessage

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

        def __init__(self, index, logc):
            self.index = index
            self.uri = "fake://index"
            if logc == "SqliteLog":
                self.log = setup_sqlite_log(self.uri)
            else:
                self.log = MemoryLog()
            self.ops = DictTotalsOps(self)

        async def process_command(self, command, serial):
            last_index = await self.log.get_last_index()
            rec = LogRec(index=last_index + 1, term=1, command=command, committed=True, applied=True)
            await self.log.append(rec)
            await self.ops.process_command(command, serial)

    
    for logc in [MemoryLog, SqliteLog]:
        fs1 = FakeServer(1, logc)
        ops1 = fs1.ops
    
        for i in range(1, 11):
            command = f'add {i} {random.randint(1,100)}'
            await fs1.process_command(command, i)
        assert len(ops1.totals) == 10
        ss1 = await fs1.ops.take_snapshot()
        await fs1.log.install_snapshot(ss1)
        assert len(ops1.snap_data) == 10
        assert await fs1.log.read(ss1.last_index) is None
        assert await fs1.log.get_first_index() is None
        assert await fs1.log.read(ss1.last_index + 1) is None
        assert await fs1.log.get_last_index() == ss1.last_index
        assert await fs1.log.get_last_term() == 1
        assert len(ops1.snap_data) == 10
        assert len(ops1.snap_data) == 10
        
        fs2 = FakeServer(2, logc)
        ops2 = fs2.ops
        # this is what a pilot should do on a call to begin_snapshot_import
        ss2 = await ops2.begin_snapshot_import(ss1.last_index, ss1.last_term)
        
        offset = 0
        done = False

        while not done:
            chunk, new_offset, done = await ss1.tool.get_snapshot_chunk(offset)
            await ss2.tool.load_snapshot_chunk(chunk)
            offset = new_offset
        await fs2.log.install_snapshot(ss2)
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
        chunk, new_offset, done = await ts_1_ss.tool.get_snapshot_chunk(offset)
        await tool_4.load_snapshot_chunk(chunk)
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
        
    # now make sure that the message interceptors work for out of sync messages

    msg = await ts_2.do_next_in_msg()
    while msg:
        msg = await ts_2.do_next_in_msg()
    ssm = SnapShotMessage(sender='mcpy://2', receiver='mcpy://1', term=1, prevLogIndex=0, prevLogTerm=0,
                          leaderId="mcpy://2", offset=0, done=True, data="[1,2]")
    ts_2.get_message_problem_history(clear=True)
    ts_2.in_messages.append(ssm)
    await ts_2.do_next_in_msg()
    res = ts_2.get_message_problem_history(clear=True)
    assert res is not None
    assert len(res) > 0
    
    ssmr = SnapShotResponseMessage(sender='mcpy://2', receiver='mcpy://1', term=1, prevLogIndex=0, prevLogTerm=0,
                          offset=0, success=True)
    ts_1.get_message_problem_history(clear=True)
    ts_1.in_messages.append(ssmr)
    await ts_1.do_next_in_msg()
    res = ts_1.get_message_problem_history(clear=True)
    assert res is not None
    assert len(res) > 0
    
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
                                     test_doc_string=test_snapshot_3.__doc__)
    await cluster.start()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]
    
    await ts_1.start_campaign()
    await cluster.run_election()
    await ts_1.send_heartbeats()
    await cluster.deliver_all_pending()
    cluster.test_trace.start_subtest("Node 1 is leader, runing commands by direct fake path")

    # The operations object maintains a dictionary of totals,
    # so "add x 1" adds one to the "x" dictionary entry.
    # We're going to use numbers as keys, and add a random value to
    # each key, 10 times.
    for i in range(10):
        for x in range(1, 11):
            command = f'add {x} {random.randint(1,100)}'
            for ts in [ts_1, ts_2, ts_3]:
                await ts.fake_command2(command)
    assert len(ts_1.operations.totals) == 10
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
        
    cluster.test_trace.start_subtest("Changing leader back to node 1 so that join will process snapshot")
    print("\n\b\nnew election\n\n")
    await new_leader.do_demote_and_handle()
    await ts_1.start_campaign()
    await cluster.run_election()
    await ts_1.send_heartbeats()
    await cluster.deliver_all_pending()
    assert await ts_2.log.get_last_index() == await ts_1.log.get_last_index()
    assert await ts_3.log.get_last_index() == await ts_1.log.get_last_index()
    
    ts_4 = await cluster.add_node()
    
    done_by_callback = None
    async def join_done(ok, new_uri):
        nonlocal done_by_callback
        logger.debug(f"\nJoin callback said {ok} joining as {new_uri}\n")
        done_by_callback = ok
    await ts_4.start_and_join(ts_1.uri, join_done)
    start_time = time.time()
    while time.time() - start_time < 0.1:
        cc = await ts_1.log.get_cluster_config()
        if ts_4.uri in cc.nodes:
            break
        await cluster.deliver_all_pending()
        await asyncio.sleep(0.001)

    assert await ts_4.log.get_first_index() == await ts_1.log.get_first_index()
    assert await ts_4.log.get_last_index() == await ts_1.log.get_last_index()
    assert await ts_2.log.get_last_index() == await ts_1.log.get_last_index()
    assert await ts_3.log.get_last_index() == await ts_1.log.get_last_index()


async def test_snapshot_4(cluster_maker):
    """
    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """
    cluster = cluster_maker(3)
    config = cluster.build_cluster_config(use_pre_vote=False)
    cluster.set_configs(config, use_ops=DictTotalsOps)

    cluster.test_trace.start_subtest("Starting election at node 1 of 3",
                                     test_path_str=str('/'.join(Path(__file__).parts[-2:])),
                                     test_doc_string=test_snapshot_4.__doc__)
    await cluster.start()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]
    
    await ts_1.start_campaign()
    await cluster.run_election()
    await ts_1.send_heartbeats()
    await cluster.deliver_all_pending()
    cluster.test_trace.start_subtest("Node 1 is leader, runing commands by direct fake path")

    # The operations object maintains a dictionary of totals,
    # so "add x 1" adds one to the "x" dictionary entry.
    # We're going to use numbers as keys, and add a random value to
    # each key, 10 times.
    for i in range(10):
        for x in range(1, 11):
            command = f'add {x} {random.randint(1,100)}'
            for ts in [ts_1, ts_2, ts_3]:
                await ts.fake_command2(command)
    assert len(ts_1.operations.totals) == 10
    last_index = await ts_1.log.get_last_index()
    last_term = await ts_1.log.get_last_term()
    rec = await ts_1.log.read(last_index)
    cluster.test_trace.start_subtest(f"Blocking {ts_3.uri} so it gets behind when next command is run, running command")
    ts_3.block_network()
    command = "add 1 1"
    await ts_1.fake_command2(command)
    await ts_2.fake_command2(command)
    assert await ts_3.log.get_last_index() < await ts_2.log.get_last_index()
    cluster.test_trace.start_subtest(f"{ts_3.uri} is behind {ts_2.uri}, making snapshot at {ts_2.uri}")
    ts_2_ss = await ts_2.take_snapshot()
    cluster.test_trace.start_subtest("Telling leader node (node 1) to resign and letting {ts_2.uri} get elected")

    await ts_1.do_demote_and_handle()
    await ts_2.start_campaign(authorized=True)
    await cluster.run_election()
    assert cluster.get_leader().uri == ts_2.uri
    await ts_2.send_heartbeats()
    await cluster.deliver_all_pending()

    cluster.test_trace.start_subtest("{ts_2.uri} now leader, unblocking {ts_3.uri}, catchup message should cause snashot install")
    ts_3.unblock_network()

    await ts_2.send_heartbeats()
    start_time = time.time()
    while time.time() - start_time < 0.1 and await ts_3.log.get_last_index() < await ts_2.log.get_last_index():
        await cluster.deliver_all_pending()
        await asyncio.sleep(0.001)
    
    assert await ts_3.log.get_last_index() == await ts_2.log.get_last_index()
    assert await ts_3.log.get_first_index() == await ts_2.log.get_first_index()
    assert await ts_3.log.get_first_index() > await ts_1.log.get_first_index()
    
async def test_snapshot_5(cluster_maker, log_class=MemoryLog):
    """
    Test persistent snapshot process, snapshotting a follower in a quiet cluster. After
    it is installed, have node that restart, then  become the leader and make sure new commands
    work.

    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    
    """
    cluster = cluster_maker(3, use_log=SqliteLog)
    config = cluster.build_cluster_config(use_pre_vote=False)
    cluster.set_configs(config, use_ops=DictTotalsOps)

    cluster.test_trace.start_subtest("Starting election at node 1 of 3",
                                     test_path_str=str('/'.join(Path(__file__).parts[-2:])),
                                     test_doc_string=test_snapshot_5.__doc__)
    await cluster.start()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]
    
    await ts_1.start_campaign()
    await cluster.run_election()
    await ts_1.send_heartbeats()
    await cluster.deliver_all_pending()
    cluster.test_trace.start_subtest("Node 1 is leader, runing commands by direct fake path")

    for x in range(1, 10):
        command = f'add {x} {random.randint(1,100)}'
        for ts in [ts_1, ts_2, ts_3]:
            command_result = await cluster.run_command(command, 1)
                
    cluster.test_trace.start_subtest("Crashing node 3, running a command, then taking snapshot at node 2")
    logger.debug(f"\ncrash 3, run command\n")
    await ts_3.simulate_crash()
    command_result = await cluster.run_command("add 1 1", 1)
    last_index = await ts_2.log.get_last_index()
    last_term = await ts_2.log.get_last_term()
    rec = await ts_2.log.read(last_index)
    logger.debug(f"\nnode 2 take snapshot\n")
    ts_2_ss = await ts_2.take_snapshot()

    # log should now be empty
    assert await ts_2.log.read(last_index) is None
    assert await ts_2.log.get_first_index() is None
    assert await ts_2.log.read(last_index + 1) is None
    assert await ts_2.log.get_last_index() == ts_2_ss.last_index
    assert await ts_2.log.get_last_term() == 1

    cluster.test_trace.start_subtest("Node 2 has snapshot and empty log, switching it to leader")
        
    logger.debug(f"\nnode 2 election\n")
    await ts_1.do_demote_and_handle()
    await ts_2.start_campaign(authorized=True)
    await cluster.run_election()
    assert ts_2.hull.is_leader()
    assert ts_1.hull.is_leader() is False
    await ts_2.send_heartbeats()
    await cluster.deliver_all_pending()
    logger.debug(f"\nnode 2 leader\n")
    assert await ts_2.log.get_last_term() == 2
    assert await ts_2.log.get_last_index() == ts_2_ss.last_index + 1
    assert await ts_2.log.get_first_index() == ts_2_ss.last_index + 1
    term_start_rec = await ts_2.log.read()
    assert term_start_rec is not None
    assert term_start_rec.index == last_index + 1
    assert term_start_rec.term == 2
    assert await ts_2.log.get_last_index() == last_index + 1

    cluster.test_trace.start_subtest("Restarting node 3, should be behind enough to need snapshot transfer")
    logger.debug(f"\nrestert node 3\n")
    await ts_3.recover_from_crash()
    await ts_2.send_heartbeats()
    await cluster.deliver_all_pending()
    assert await ts_2.log.get_last_index() == await ts_3.log.get_last_index()
    assert await ts_2.log.get_first_index() == await ts_3.log.get_first_index()
        
