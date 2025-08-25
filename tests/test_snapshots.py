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
from raftengine.api.deck_config import ClusterInitConfig
from raftengine.api.snapshot_api import SnapShot
from raftengine_logs.memory_log import MemoryLog
from raftengine_logs.sqlite_log import SqliteLog
from dev_tools.sequences import SNormalElection, SNormalCommand, SPartialElection, SPartialCommand
from dev_tools.log_control import setup_logging
from dev_tools.pausing_cluster import PausingCluster, cluster_maker
from dev_tools.pausing_server import setup_log
from dev_tools.operations import DictTotalsOps, SnapShotTool
from raftengine.messages.snapshot import SnapShotMessage, SnapShotResponseMessage

log_control = setup_logging()
logger = logging.getLogger("test_code")


async def test_dict_ops():
    """
    Tests dictionary operations for snapshot functionality without Raft operations.
    """
    class FakeServer:

        def __init__(self, index, logc):
            self.index = index
            self.uri = "fake://index"
            if logc == "SqliteLog":
                self.log = setup_log(self.uri, use_log_class=SqliteLog)
            else:
                self.log = MemoryLog()
            self.ops = DictTotalsOps(self)

        async def process_command(self, command, serial):
            last_index = await self.log.get_last_index()
            rec = LogRec(index=last_index + 1, term=1, command=command)
            await self.log.append(rec)
            await self.log.mark_committed(rec.index)
            await self.ops.process_command(command, serial)
            await self.log.mark_applied(rec.index)

    
    for logc in [MemoryLog, SqliteLog]:
        fs1 = FakeServer(1, logc)
        ops1 = fs1.ops
    
        for i in range(1, 11):
            command = f'add {i} {random.randint(1,100)}'
            await fs1.process_command(command, i)
        assert len(ops1.totals) == 10
        last_applied = await fs1.log.get_applied_index()
        last_rec  = await fs1.log.read(last_applied)
        ss1 = await fs1.ops.create_snapshot(last_applied, last_rec.term)
        await fs1.log.install_snapshot(ss1)
        assert len(ops1.snap_data) == 10
        assert await fs1.log.read(ss1.index) is None
        assert await fs1.log.get_first_index() is None
        assert await fs1.log.read(ss1.index + 1) is None
        assert await fs1.log.get_last_index() == ss1.index
        assert await fs1.log.get_last_term() == 1
        assert len(ops1.snap_data) == 10
        assert len(ops1.snap_data) == 10

        tool1 = SnapShotTool(fs1.ops, fs1.log, ss1)
        
        fs2 = FakeServer(2, logc)
        ops2 = fs2.ops
        ss2 = SnapShot(ss1.index, ss1.term)
        tool2 = await ops2.begin_snapshot_import(ss2)
        
        offset = 0
        done = False

        while not done:
            chunk, new_offset, done = await tool1.get_snapshot_chunk(offset)
            await tool2.load_snapshot_chunk(chunk)
            offset = new_offset
        await fs2.log.install_snapshot(ss2)
        for key in ops1.totals:
            assert ops1.totals[key] == ops2.totals[key]
    
async def test_snapshot_1(cluster_maker):
    """
    Tests the mechanisms in the dev_tools test support code that implement snapshot operations.
    Doesn't do any snapshot work with the raft operations, just establishes that the "state machine"
    snapshot creation and use works.

    No raft operations are run, so the traces will contain only the node start trace.
    """
    cluster = cluster_maker(3)
    tconfig = cluster.build_cluster_config()
    cluster.set_configs(use_ops=DictTotalsOps)
    await cluster.test_trace.define_test("Testing snapshot mechanisms in dev_tools", logger=logger)

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
    assert await ts_1.log.get_last_index() == ts_1_ss.index
    assert await ts_1.log.get_last_term() == 1
    assert await ts_1.log.get_last_term() == ts_1_ss.term

    tool1 = await ts_1.begin_snapshot_export(ts_1_ss)
    ts_4 = await cluster.add_node()
    tool4 = await ts_4.begin_snapshot_import(ts_1_ss)
    offset = 0
    done = False
    while not done:
        chunk, new_offset, done = await tool1.get_snapshot_chunk(offset)
        await tool4.load_snapshot_chunk(chunk)
        offset = new_offset
    await tool4.log.start()
    snap = await tool4.apply_snapshot()
    await ts_4.log.install_snapshot(snap)
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

    await cluster.test_trace.define_test("Testing simplest snapshot process at a follower", logger=logger)
    await cluster.test_trace.start_test_prep("Running election to elect node 1")
    await cluster.start()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]
    
    await ts_1.start_campaign()
    await cluster.run_election()
    await cluster.test_trace.start_subtest("Node 1 is leader, runing commands by indirect fake path")

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
    assert await ts_2.log.get_last_index() == ts_2_ss.index
    assert await ts_2.log.get_last_term() == 1

    await cluster.test_trace.start_subtest("Node 2 has snapshot and empty log, switching it to leader")
        
    await ts_1.do_demote_and_handle()
    await ts_2.start_campaign(authorized=True)
    await cluster.run_election()
    assert ts_2.deck.is_leader()
    assert ts_1.deck.is_leader() is False
    assert await ts_2.log.get_last_term() == 2
    assert await ts_2.log.get_first_index() == ts_2_ss.index + 1
    assert await ts_2.log.get_last_index() == ts_2_ss.index + 1
    term_start_rec = await ts_2.log.read()
    assert term_start_rec is not None
    assert term_start_rec.index == last_index + 1
    assert term_start_rec.term == 2
    assert await ts_2.log.get_last_index() == last_index + 1

    command_result = await cluster.run_command("add 1 1", 1)
    assert await ts_2.log.get_first_index() == ts_2_ss.index + 1
    assert await ts_2.log.get_last_index() == ts_2_ss.index + 2
        
    # Now make sure that the message interceptors work for out of sync messages

    msg = await ts_2.do_next_in_msg()
    while msg:
        msg = await ts_2.do_next_in_msg()
    ssm = SnapShotMessage(sender='mcpy://2', receiver='mcpy://1', term=1, prevLogIndex=0, prevLogTerm=0,
                          leaderId="mcpy://2", offset=0, done=True, data="[1,2]")
    ts_2.get_message_problem_history(clear=True)
    ts_2.in_messages.append(ssm)
    await ts_2.do_next_in_msg()
    assert len(ts_2.out_messages) > 0
    assert ts_2.out_messages[0].code == SnapShotResponseMessage.code
    assert ts_2.out_messages[0].success is False
    
    ssmr = SnapShotResponseMessage(sender='mcpy://2', receiver='mcpy://1', term=1, prevLogIndex=0, prevLogTerm=0,
                          offset=0, success=True)
    ts_1.in_messages.append(ssmr)
    # just make sure it doesn't explode
    await ts_1.do_next_in_msg()
    await cluster.test_trace.end_subtest()
    
    
async def test_snapshot_3(cluster_maker):
    """
    Test the snapshot process when the leader is told to snapshot. It should
    transfer power and then do the snapshot, then rejoin cluster. Also tests
    that a node joining the cluster will get the snapshot installed during
    pre-add log loading.

    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """
    cluster = cluster_maker(3)
    config = cluster.build_cluster_config(use_pre_vote=False)
    cluster.set_configs(config, use_ops=DictTotalsOps)

    await cluster.test_trace.define_test("Testing snapshot process when leader is told to snapshot", logger=logger)
    await cluster.test_trace.start_test_prep("Running election to elect node 1")
    await cluster.start()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]
    
    await ts_1.start_campaign()
    await cluster.run_election()
    await ts_1.send_heartbeats()
    await cluster.deliver_all_pending()
    await cluster.test_trace.start_subtest("Node 1 is leader, runing commands by indirect fake path")

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
    await cluster.test_trace.start_subtest("Telling leader node (node 1) to snapshot but blocking net, should fail because it can't transfer power")
    with pytest.raises(Exception):
        ts_1_ss = await ts_1.take_snapshot(timeout=0.05)
    await cluster.test_trace.start_subtest("Telling leader node (node 1) to snapshot, should make it transfer power")
    await cluster.start_auto_comms()
    ts_1_ss = await ts_1.take_snapshot()
    await cluster.stop_auto_comms()
    assert ts_1.deck.is_leader() is False
    new_leader = cluster.get_leader()
    # sometimes the old leader does not get the new leader's uri instantly,
    # there is a timing issue, if the new leader's TERM START hansing hit yet
    start_time = time.time()
    while new_leader is None and time.time() - start_time < 0.1:
        await asyncio.sleep(0.0001)
        await cluster.deliver_all_pending()
        new_leader = cluster.get_leader()
    assert ts_1.deck.leader_uri == new_leader.uri
    
    # log should now have only the term start record
    assert await ts_1.log.read(last_index) is None
    assert await ts_1.log.get_first_index() == last_index + 1
    assert await ts_1.log.get_last_index() == ts_1_ss.index + 1
    assert await ts_1.log.read(last_index + 1) is not None
    assert await ts_1.log.get_last_term() == 2

    assert await new_leader.log.read(last_index) is not None
    assert await new_leader.log.get_first_index() is not None
    assert await new_leader.log.read(last_index + 1) is not None
    assert await new_leader.log.get_last_index() == ts_1_ss.index + 1
    assert await new_leader.log.get_last_term() == 2

    await cluster.test_trace.start_subtest("Node 1 has snapshot and empty log, {new_leader.uri} is leader, running command")
        
    command_result = await cluster.run_command("add 1 1", 1)
    assert await ts_1.log.get_first_index() == ts_1_ss.index + 1
    assert await ts_1.log.get_last_index() == ts_1_ss.index + 2
        
    await cluster.test_trace.start_subtest("Changing leader back to node 1 so that join will process snapshot")
    await new_leader.do_demote_and_handle()
    await ts_1.start_campaign()
    await cluster.run_election()
    await ts_1.send_heartbeats()
    await cluster.deliver_all_pending()
    assert await ts_2.log.get_last_index() == await ts_1.log.get_last_index()
    assert await ts_3.log.get_last_index() == await ts_1.log.get_last_index()
    
    await cluster.test_trace.start_subtest("Adding a node to and checking that it receives snapshot before joining")
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
    Tests that a node that is "slow" will get a snapshot installed when it falls behind
    a leader that has a snapshot that extends beyond the slow node's log index.
    It uses the dev_tools SqliteLog instead of the usual MemoryLog to ensure that nothing
    about the snapshot operations fails after restart.

    The process is to run an election, crash node 3, run another command so that node 1 (leader)
    and node 2 are both ahead on log index. Next a snapshot is created at node 2, and then an
    election is held to force node 2 to be leader. Next node 3 is restarted, and the details
    of log values are checked to make sure that node 3 installed the snapshot before catching
    up normally.
    
    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    
    """
    cluster = cluster_maker(3, use_log=SqliteLog)
    config = cluster.build_cluster_config(use_pre_vote=False)
    cluster.set_configs(config, use_ops=DictTotalsOps)

    await cluster.test_trace.define_test("Testing snapshot installation on a slow follower", logger=logger)
    await cluster.test_trace.start_test_prep("Running election to elect node 1")
    await cluster.start()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]
    
    await ts_1.start_campaign()
    await cluster.run_election()
    await ts_1.send_heartbeats()
    await cluster.deliver_all_pending()
    await cluster.test_trace.start_subtest("Node 1 is leader, runing commands ")

    for x in range(1, 6):
        command = f'add {x} {random.randint(1,100)}'
        for ts in [ts_1, ts_2, ts_3]:
            command_result = await cluster.run_command(command, 1)
                
    await cluster.test_trace.start_subtest("Crashing node 3, running a command, then taking snapshot at node 2")
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
    assert await ts_2.log.get_last_index() == ts_2_ss.index
    assert await ts_2.log.get_last_term() == 1

    await cluster.test_trace.start_subtest("Node 2 has snapshot and empty log, switching it to leader")
        
    logger.debug(f"\nnode 2 election\n")
    await ts_1.do_demote_and_handle()
    await ts_2.start_campaign(authorized=True)
    await cluster.run_election()
    assert ts_2.deck.is_leader()
    assert ts_1.deck.is_leader() is False
    await ts_2.send_heartbeats()
    await cluster.deliver_all_pending()
    logger.debug(f"\nnode 2 leader\n")
    assert await ts_2.log.get_last_term() == 2
    assert await ts_2.log.get_last_index() == ts_2_ss.index + 1
    assert await ts_2.log.get_first_index() == ts_2_ss.index + 1
    term_start_rec = await ts_2.log.read()
    assert term_start_rec is not None
    assert term_start_rec.index == last_index + 1
    assert term_start_rec.term == 2
    assert await ts_2.log.get_last_index() == last_index + 1

    await cluster.test_trace.start_subtest("Restarting node 3, should be behind enough to need snapshot transfer")
    logger.debug(f"\nrestert node 3\n")
    await ts_3.recover_from_crash()
    await ts_2.send_heartbeats()
    await cluster.deliver_all_pending()
    assert await ts_2.log.get_last_index() == await ts_3.log.get_last_index()
    assert await ts_2.log.get_first_index() == await ts_3.log.get_first_index()
