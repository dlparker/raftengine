#!/usr/bin/env python
import logging
from pathlib import Path
import time
import asyncio
import pytest

from raftengine.messages.append_entries import AppendEntriesMessage, AppendResponseMessage
from raftengine.api.events import EventType, EventHandler
from raftengine.api.pilot_api import PilotAPI
from raftengine.api.log_api import LogRec, RecordCode
from raftengine.api.types import NodeRec, ClusterConfig, ClusterSettings
from raftengine.deck.deck import Deck
from raftengine.api.snapshot_api import SnapShot
from raftengine.messages.cluster_change import MembershipChangeMessage, ChangeOp, MembershipChangeResponseMessage
from dev_tools.triggers import WhenMessageOut, WhenMessageIn
from dev_tools.sequences import SPartialElection
from raftengine_logs.memory_log import MemoryLog
from dev_tools.pausing_cluster import cluster_maker
from dev_tools.log_control import setup_logging

#extra_logging = [dict(name=__name__, level="debug"),]
#setup_logging(extra_logging)
default_level="error"
#default_level="debug"
log_control = setup_logging()
logger = logging.getLogger("test_code")

class PilotSim(PilotAPI):

    def __init__(self, log):
        self.log = log

    def get_log(self):
        return self.log
    
    async def process_command(self, command: str, serial: int):
        raise NotImplementedError

    async def send_message(self, target_uri: str, message:str, serial_number: int):
        raise NotImplementedError

    async def send_response(self, target_uri: str, orig_message:str, reply:str, orig_serial_number: int):
        raise NotImplementedError

    async def stop_commanded(self) -> None:
        raise NotImplementedError

    async def begin_snapshot_import(self, index, term):
        raise NotImplementedError

    async def begin_snapshot_export(self, snapshot):
        raise NotImplementedError
    
    async def create_snapshot(self, index:int , term: int) -> SnapShot:
        raise NotImplementedError

    
async def test_member_change_messages(cluster_maker):
    """
    Test some basic features of the messages classes used to coordinate membership changes.
    """
    cluster = cluster_maker(1)
    await cluster.test_trace.define_test("Testing membership change message operations", logger=logger)
    await cluster.test_trace.start_test_prep("Normal election")
    m1 = MembershipChangeMessage('mcpy://1', 'mcpy://2', ChangeOp.add, target_uri="mcpy://4")
    r1 = MembershipChangeResponseMessage('mcpy://2', 'mcpy://1', ChangeOp.add, target_uri="mcpy://4", ok=True)
    
    assert "mcpy://4" in str(m1)
    assert m1.get_code() == "membership_change"
    assert "mcpy://4" in str(r1)
    assert "ok=True" in str(r1)
    assert r1.get_code() == "membership_change_response"
    assert r1.is_reply_to(m1)
    assert not r1.is_reply_to(r1)
    cm1 = MembershipChangeMessage.from_dict(m1.__dict__)
    assert str(cm1) == str(m1)
    assert r1.is_reply_to(cm1)
    cr1 = MembershipChangeResponseMessage.from_dict(r1.__dict__)
    assert str(cr1) == str(r1)

    
async def test_cluster_config_ops(cluster_maker):
    """
    Tests the cluster configuration operations and their database operations used to track
    the progress of membership change operations. No message or timer operations are involved.
    """
    cluster = cluster_maker(1)
    await cluster.test_trace.define_test("Testing cluster configuration operations for membership changes", logger=logger)
    await cluster.test_trace.start_test_prep("Normal election")
    cluster = cluster_maker(3)
    tconfig = cluster.build_cluster_config()
    cluster.set_configs()
    
    nd = {}
    local_config = None
    for uri in tconfig.node_uris:
        nd[uri] = NodeRec(uri)
        if local_config is None:
            local_config = cluster.nodes[uri].local_config
        
    log = MemoryLog()
    await log.start()
    
    deck = Deck(initial_cluster_config=tconfig, local_config=local_config, pilot = PilotSim(log))
    c_ops = deck.cluster_ops
    cc = await deck.get_cluster_config()
    
    uri = 'mcpy://4'
    await c_ops.start_node_add(uri)
    with pytest.raises(Exception):
        await c_ops.start_node_add('mcpy://5')
    with pytest.raises(Exception):
        await c_ops.start_node_remove(uri)
    cc4 = await c_ops.finish_node_add(uri)
    assert uri in cc4.nodes
    with pytest.raises(Exception):
        await c_ops.start_node_add(uri)
    with pytest.raises(Exception):
        await c_ops.finish_node_add(uri)
    cc5 = await c_ops.start_node_remove(uri)
    assert uri not in cc5.nodes
    with pytest.raises(Exception):
        await c_ops.start_node_add('mcpy://5')
    with pytest.raises(Exception):
        await c_ops.start_node_remove('mcpy://5')
    cc6 = await c_ops.finish_node_remove(uri)
    assert uri not in cc6.nodes
    assert cc6.pending_node is None
    with pytest.raises(Exception):
        await c_ops.start_node_remove(uri)
    with pytest.raises(Exception):
        await c_ops.finish_node_remove(uri)

    # make sure calling plan add on the same node twice returns None
    assert await c_ops.start_node_add(uri) 
    assert await c_ops.plan_add_node(uri) is None
    # make sure calling plan add on an already added node returns None
    assert await c_ops.finish_node_add(uri)
    assert await c_ops.plan_add_node(uri) is None

    # make sure calling plan remove on the same node twice returns None
    assert await c_ops.start_node_remove(uri) 
    assert await c_ops.plan_remove_node(uri) is None
    # make sure calling plan remove on an already removed node returns None
    assert await c_ops.finish_node_remove(uri)
    assert await c_ops.plan_remove_node(uri) is None

async def test_remove_follower_1(cluster_maker):
    """
    Simple case of removing a follower from the cluster. 
    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """
    
    cluster = cluster_maker(3)
    config = cluster.build_cluster_config(use_pre_vote=False)
    cluster.set_configs(config)

    await cluster.test_trace.define_test("Testing removal of a follower from the cluster", logger=logger)
    await cluster.test_trace.start_test_prep("Normal election")
    await cluster.start()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]

    await ts_1.start_campaign()
    await cluster.run_election()
    await cluster.test_trace.start_subtest("Node 1 is leader, telling node 3 to trigger cluster exit for itself.")
    logger.debug("\n\n\nRemoving node 3\n\n\n")
    # now remove number 3
    removed = None
    done_by_event = None
    async def cb(success, uri):
        nonlocal removed
        removed = success

    class MembershipChangeResultHandler(EventHandler):
        def __init__(self):
            super().__init__(event_types=[EventType.membership_change_complete,
                                          EventType.membership_change_aborted,])
            
        async def on_event(self, event):
            nonlocal done_by_event
            if event.event_type == EventType.membership_change_complete:
                done_by_event = True
                logger.debug('in handler with success = True\n')
            else:
                logger.debug('in handler with success = False\n')
                done_by_event = False
    await ts_3.deck.add_event_handler(MembershipChangeResultHandler())
    await ts_3.exit_cluster(callback=cb)
    await cluster.deliver_all_pending()
    await ts_1.send_heartbeats()
    start_time = time.time()
    while time.time() - start_time < 0.5 and removed is None:
        await cluster.deliver_all_pending()
        await asyncio.sleep(0.0001)
    assert removed is not None
    await asyncio.sleep(0.0)
    assert done_by_event is not None
    assert ts_3.deck.role.stopped

    # now make sure heartbeat send only goes to the one remaining follower
    await ts_1.send_heartbeats()
    assert len(ts_1.out_messages) == 1
    assert ts_1.out_messages[0].receiver == ts_2.uri

async def test_remove_leader_1(cluster_maker):
    """
    Simple case of removing the leader from the cluster. 
    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """
    
    cluster = cluster_maker(3)
    config = cluster.build_cluster_config(use_pre_vote=False)
    cluster.set_configs(config)

    await cluster.test_trace.define_test("Testing removal of the leader from the cluster", logger=logger)
    await cluster.test_trace.start_test_prep("Normal election")
    await cluster.start()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]

    await ts_1.start_campaign()
    await cluster.run_election()
    await cluster.test_trace.start_subtest("Node 1 is leader, telling it to exit the cluster")

    logger.debug("\n\n\nRemoving leader node 1\n\n\n")
    await ts_1.exit_cluster()
    await cluster.deliver_all_pending()
    await ts_1.send_heartbeats()
    start_time = time.time()
    while time.time() - start_time < 1.0:
        if ts_2.get_role_name() == "LEADER" or ts_3.get_role_name() == "LEADER":
            break
        if ts_1.deck is None:
            break
        await asyncio.sleep(0.01)
        await cluster.deliver_all_pending()
        
    assert ts_2.get_role_name() == "LEADER" or ts_3.get_role_name() == "LEADER"
    await asyncio.sleep(0.01)
    assert ts_1.deck.role.stopped

async def test_add_follower_1(cluster_maker):
    """
    Simple case of adding a follower to the cluster with a short log, only a term start and one command.
    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """
    
    cluster = cluster_maker(3)
    config = cluster.build_cluster_config(use_pre_vote=False)
    cluster.set_configs(config)

    await cluster.test_trace.define_test("Testing addition of a follower with a short log", logger=logger)
    await cluster.test_trace.start_test_prep("Normal election")
    await cluster.start()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]

    await ts_1.start_campaign()
    await cluster.run_election()
    await cluster.test_trace.start_subtest("Node 1 is leader, starting process off  adding node 4")
    
    command_result = await cluster.run_command("add 1", 1)
    assert ts_1.operations.total == 1
    ts_4 = await cluster.add_node()
    leader = cluster.get_leader()
    assert await ts_1.deck.get_leader_uri() == leader.uri
    async def join_done(ok, new_uri):
        logger.debug(f"Join callback said {ok} joining as {new_uri}")
        assert ok
    await ts_4.start_and_join(leader.uri, join_done)
    start_time = time.time()
    while time.time() - start_time < 0.1:
        cc = await ts_1.log.get_cluster_config()
        if ts_4.uri in cc.nodes:
            break
        await cluster.deliver_all_pending()
        await asyncio.sleep(0.001)

    assert ts_4.operations.total == 1

async def test_add_follower_2(cluster_maker):
    """
    Adding a follower to the cluster with a long log, filled with a bunch entries. We are
    cheating by directly adding the entries to each member node before the add, just to keep the
    logging, time and tracing down.
    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """
    
    cluster = cluster_maker(3)
    config = cluster.build_cluster_config(use_pre_vote=False)
    cluster.set_configs(config)

    await cluster.test_trace.define_test("Testing addition of a follower with a long log", logger=logger)
    await cluster.test_trace.start_test_prep("Normal election")
    await cluster.start()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]

    await ts_1.start_campaign()
    await cluster.run_election()
    await cluster.test_trace.start_subtest("Node 1 is leader, inserting some records via indirect acceess to logs")

    msg_per = await ts_1.deck.get_max_entries_per_message()
    limit = (msg_per *3) + 2 # get three blocks of update, will start at 2 because we have one record already
    for i in range(2, limit+1):
        for ts in [ts_1, ts_2, ts_3]:
            await ts.fake_command("add", 1)
    for ts in [ts_1, ts_2, ts_3]:
        assert await ts.log.get_last_term() == 1
        assert await ts.log.get_last_index() == limit
        assert await ts.log.get_commit_index() == limit
        assert await ts.log.get_applied_index() == limit
        ts.operations.total == limit - 1
    ts_4 = await cluster.add_node()
    leader = cluster.get_leader()
    done_by_callback = None
    done_by_event = None
    async def join_done(ok, new_uri):
        nonlocal done_by_callback
        logger.debug(f"\nJoin callback said {ok} joining as {new_uri}\n")
        done_by_callback = ok
        
    class MembershipChangeResultHandler(EventHandler):
        def __init__(self):
            super().__init__(event_types=[EventType.membership_change_complete,
                                          EventType.membership_change_aborted,])
            
        async def on_event(self, event):
            nonlocal done_by_event
            if event.event_type == EventType.membership_change_complete:
                done_by_event = True
                logger.debug('in handler with success = True\n')
            else:
                logger.debug('in handler with success = False\n')
                done_by_event = False
    class MembershipChangeResultHandler(EventHandler):
        def __init__(self):
            super().__init__(event_types=[EventType.membership_change_complete,
                                          EventType.membership_change_aborted,])
            
        async def on_event(self, event):
            nonlocal done_by_event
            if event.event_type == EventType.membership_change_complete:
                done_by_event = True
                logger.debug('in handler with success = True\n')
            else:
                logger.debug('in handler with success = False\n')
                done_by_event = False

    logger.debug("\n\nStarting join from node 4\n\n")
    await cluster.test_trace.start_subtest("Records inserted, starting add of node 4")
    await ts_4.deck.add_event_handler(MembershipChangeResultHandler())
    await ts_4.start_and_join(leader.uri, join_done)
    start_time = time.time()
    while time.time() - start_time < 0.1:
        cc = await ts_1.log.get_cluster_config()
        if ts_4.uri in cc.nodes:
            break
        await cluster.deliver_all_pending()
        await asyncio.sleep(0.001)

    assert ts_4.operations.total == ts_1.operations.total
    await asyncio.sleep(0.00)
    assert done_by_callback 
    assert done_by_event 
    
async def test_add_follower_2_rounds_1(cluster_maker):
    """
    Adding a follower to the cluster with intervention to ensure that more than one round of log catch up
    happens. This occurs when new records are added to the leader's log before the leader receives acknowledgement
    that all of the records in the first round of pre-join log updates happened.
    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """
    
    cluster = cluster_maker(3)
    config = cluster.build_cluster_config(use_pre_vote=False)
    cluster.set_configs(config)

    await cluster.test_trace.define_test("Testing addition of a follower with multiple log catch-up rounds", logger=logger)
    await cluster.test_trace.start_test_prep("Normal election")
    await cluster.start()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]

    await ts_1.start_campaign()
    await cluster.run_election()
    await cluster.test_trace.start_subtest("Node 1 is leader, adding records to log via indirect insert")

    msg_per = await ts_1.deck.get_max_entries_per_message()
    limit = int(msg_per/2) + 2 # get just one block to update, index starts at two because of term start log entry
    for i in range(2, limit+1):
        for ts in [ts_1, ts_2, ts_3]:
            await ts.fake_command("add", 1)
    for ts in [ts_1, ts_2, ts_3]:
        assert await ts.log.get_last_term() == 1
        assert await ts.log.get_last_index() == limit
        assert await ts.log.get_commit_index() == limit
        assert await ts.log.get_applied_index() == limit
        assert ts.operations.total == limit - 1
    ts_4 = await cluster.add_node()
    leader = cluster.get_leader()
    done_by_callback = None
    done_by_event = None
    async def join_done(ok, new_uri):
        nonlocal done_by_callback
        logger.debug(f"\nJoin callback said {ok} joining as {new_uri}\n")
        done_by_callback = ok
        
    class MembershipChangeResultHandler(EventHandler):
        def __init__(self):
            super().__init__(event_types=[EventType.membership_change_complete,
                                          EventType.membership_change_aborted,])
            
        async def on_event(self, event):
            nonlocal done_by_event
            if event.event_type == EventType.membership_change_complete:
                done_by_event = True
                logger.debug('in handler with success = True\n')
            else:
                logger.debug('in handler with success = False\n')
                done_by_event = False

    # first exchange will tell leader that node 4 needs catchup, by
    # how much from maxIndex in response
    await ts_4.deck.add_event_handler(MembershipChangeResultHandler())
    await ts_4.start_and_join(leader.uri, join_done)

    ts_1.set_trigger(WhenMessageIn(AppendResponseMessage.get_code()))
    ts_4.set_trigger(WhenMessageOut(AppendResponseMessage.get_code()))
    await asyncio.gather(ts_1.run_till_triggers(),
                         ts_4.run_till_triggers())
    ts_1.clear_triggers()
    ts_4.clear_triggers()
    logger.debug("\n\nappend 1 done, should backdown\n\n")
    await ts_1.do_next_in_msg()
    assert ts_1.out_messages[0].code == AppendEntriesMessage.get_code()
    await ts_1.do_next_out_msg()
    assert ts_4.in_messages[0].code == AppendEntriesMessage.get_code()
    await ts_4.do_next_in_msg()
    assert ts_4.out_messages[0].code == AppendResponseMessage.get_code()
    await ts_4.do_next_out_msg()
    # this last exchange was the backdown, should result in replicating record 1, term start
    # next should replicate the command records
    logger.debug("\n\nappend 2 done, backdown should be done, now catchup\n\n")
    await ts_1.do_next_in_msg()
    assert ts_1.out_messages[0].code == AppendEntriesMessage.get_code()
    await ts_1.do_next_out_msg()
    assert ts_4.in_messages[0].code == AppendEntriesMessage.get_code()
    await ts_4.do_next_in_msg()
    assert ts_4.out_messages[0].code == AppendResponseMessage.get_code()

    assert await ts_4.log.get_last_index() == limit
    assert await ts_4.log.get_commit_index() == limit
    assert ts_4.operations.total == limit - 1

    await cluster.test_trace.start_subtest("New node has added all first round records, but leader not yet informed, adding new records")
    logger.debug("\n\nappend 3 done, node 4 caught up but leader doesn't know yet, faking commands\n")
    await ts_1.fake_command("add", 1)
    logger.debug("\n\nfaked command at leader, should start round 2 now\n")
    
    await ts_4.do_next_out_msg()
    
    start_time = time.time()
    while time.time() - start_time < 0.1:
        cc = await ts_1.log.get_cluster_config()
        if ts_4.uri in cc.nodes:
            break
        await cluster.deliver_all_pending()
        await asyncio.sleep(0.001)

    assert ts_4.operations.total == ts_1.operations.total
    await asyncio.sleep(0.001)
    assert done_by_callback 
    assert done_by_event 
    
async def test_add_follower_3_rounds_1(cluster_maker):
    """
    Adding a follower to the cluster with intervention to ensure that three rounds of log catch up
    happen. This occurs when new records are added to the leader's log before the leader receives acknowledgement
    that all of the records in the previous round of pre-join log updates happened. So the test method is to
    pause the leader just before it receives the append entries response that completes a round and to
    insert new log records so that the pre-join log sync process will trigger another round.
    
    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """
    
    cluster = cluster_maker(3)
    config = cluster.build_cluster_config(use_pre_vote=False)
    cluster.set_configs(config)

    await cluster.test_trace.define_test("Testing addition of a follower with three log catch-up rounds", logger=logger)
    await cluster.test_trace.start_test_prep("Normal election")
    await cluster.start()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]

    await ts_1.start_campaign()
    await cluster.run_election()
    await cluster.test_trace.start_subtest("Node 1 is leader, loading log records and then starting add of node 4")

    msg_per = await ts_1.deck.get_max_entries_per_message()
    limit = int(msg_per/2) + 2 # get just one block to update, index starts at two because of term start log entry
    for i in range(2, limit+1):
        for ts in [ts_1, ts_2, ts_3]:
            await ts.fake_command("add", 1)
    for ts in [ts_1, ts_2, ts_3]:
        assert await ts.log.get_last_term() == 1
        assert await ts.log.get_last_index() == limit
        assert await ts.log.get_commit_index() == limit
        assert await ts.log.get_applied_index() == limit
        assert ts.operations.total == limit - 1
    ts_4 = await cluster.add_node()
    leader = cluster.get_leader()
    done_by_callback = None
    done_by_event = None
    async def join_done(ok, new_uri):
        nonlocal done_by_callback
        logger.debug(f"\nJoin callback said {ok} joining as {new_uri}\n")
        done_by_callback = ok
        
    class MembershipChangeResultHandler(EventHandler):
        def __init__(self):
            super().__init__(event_types=[EventType.membership_change_complete,
                                          EventType.membership_change_aborted,])
            
        async def on_event(self, event):
            nonlocal done_by_event
            if event.event_type == EventType.membership_change_complete:
                done_by_event = True
                logger.debug('in handler with success = True\n')
            else:
                logger.debug('in handler with success = False\n')
                done_by_event = False

    # first exchange will tell leader that node 4 needs catchup, by
    # how much from maxIndex in response
    await ts_4.deck.add_event_handler(MembershipChangeResultHandler())
    await ts_4.start_and_join(leader.uri, join_done)

    ts_1.set_trigger(WhenMessageIn(AppendResponseMessage.get_code()))
    ts_4.set_trigger(WhenMessageOut(AppendResponseMessage.get_code()))
    await asyncio.gather(ts_1.run_till_triggers(),
                         ts_4.run_till_triggers())
    ts_1.clear_triggers()
    ts_4.clear_triggers()
    logger.debug("\n\nappend 1 done, should backdown\n\n")
    await ts_1.do_next_in_msg()
    assert ts_1.out_messages[0].code == AppendEntriesMessage.get_code()
    await ts_1.do_next_out_msg()
    assert ts_4.in_messages[0].code == AppendEntriesMessage.get_code()
    await ts_4.do_next_in_msg()
    assert ts_4.out_messages[0].code == AppendResponseMessage.get_code()
    await ts_4.do_next_out_msg()
    # this last exchange was the backdown, should result in replicating record 1, term start
    # next should replicate the command records
    logger.debug("\n\nappend 2 done, backdown should be done, now catchup\n\n")
    await ts_1.do_next_in_msg()
    assert ts_1.out_messages[0].code == AppendEntriesMessage.get_code()
    await ts_1.do_next_out_msg()
    assert ts_4.in_messages[0].code == AppendEntriesMessage.get_code()
    await ts_4.do_next_in_msg()
    assert ts_4.out_messages[0].code == AppendResponseMessage.get_code()

    assert await ts_4.log.get_last_index() == limit
    assert await ts_4.log.get_commit_index() == limit
    assert ts_4.operations.total == limit - 1

    await cluster.test_trace.start_subtest("Node 4 caught up, adding new records before letting leader know that")
    logger.debug("\n\nappend 3 done, node 4 caught up but leader doesn't know yet, faking command to start a round\n")
    last_index = await ts_4.log.get_last_index()
    await ts_1.fake_command("add", 1)
    logger.debug("\n\nfaked command at leader, should start round 2 now\n")
    
    await ts_4.do_next_out_msg()
    await ts_1.do_next_in_msg()
    # these asserts don't test much, but they help readers understand what it happening
    assert ts_1.out_messages[0].code == AppendEntriesMessage.get_code()
    await ts_1.do_next_out_msg()
    assert ts_4.in_messages[0].code == AppendEntriesMessage.get_code()
    await ts_4.do_next_in_msg()
    assert ts_4.out_messages[0].code == AppendResponseMessage.get_code()

    # poised to finish round 2, add more commands to force round 3, and make it enough to take > 1 message
    await cluster.test_trace.start_subtest("Node 4 caught up on roudn 2, adding new records before letting leader know that")
    msg_per = await ts_1.deck.get_max_entries_per_message()
    limit = int(msg_per*2)
    for i in range(limit):
        for ts in [ts_1, ts_2, ts_3]:
            await ts.fake_command("add", 1)
    logger.debug(f"\n\nfaked {limit} commands at leader, should start round 3 now\n")

    await ts_4.do_next_out_msg()
    
    start_time = time.time()
    while time.time() - start_time < 0.1:
        cc = await ts_1.log.get_cluster_config()
        if ts_4.uri in cc.nodes:
            break
        await cluster.deliver_all_pending()
        await asyncio.sleep(0.001)

    assert ts_4.operations.total == ts_1.operations.total
    assert done_by_callback 
    await asyncio.sleep(0.00)
    assert done_by_event 
    
async def test_add_follower_too_many_rounds_1(cluster_maker):
    """
    Tests that the membership change process will abort the add node process when the new node fails
    to catch up on all log records in 10 rounds of updates. This is accomplished by intercepting
    the append entries responses that indicate that the new node has finished appending the records
    for the current round ov updates and adding new records to the leader's log (and to the other followers)
    so that the leader starts another round. This is done until ten rounds have been completed, at which
    point the leader should abort the add. 
    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """
    
    cluster = cluster_maker(3)
    config = cluster.build_cluster_config(use_pre_vote=False)
    cluster.set_configs(config)

    await cluster.test_trace.define_test("Testing abort of follower addition due to too many log catch-up rounds", logger=logger)
    await cluster.test_trace.start_test_prep("Normal election")
    await cluster.start()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]

    await ts_1.start_campaign()
    await cluster.run_election()
    await cluster.test_trace.start_subtest("Node 1 is leader, inserting some records via indirect acceess to logs")

    msg_per = await ts_1.deck.get_max_entries_per_message()
    limit = int(msg_per/2) + 2 # get just one block to update, index starts at two because of term start log entry
    for i in range(2, limit+1):
        for ts in [ts_1, ts_2, ts_3]:
            await ts.fake_command("add", 1)
    for ts in [ts_1, ts_2, ts_3]:
        assert await ts.log.get_last_term() == 1
        assert await ts.log.get_last_index() == limit
        assert await ts.log.get_commit_index() == limit
        assert await ts.log.get_applied_index() == limit
        assert ts.operations.total == limit - 1
    ts_4 = await cluster.add_node()
    leader = cluster.get_leader()
    done_by_callback = None
    done_by_event = None
    async def join_done(ok, new_uri):
        nonlocal done_by_callback
        logger.debug(f"\nJoin callback said {ok} joining as {new_uri}\n")
        done_by_callback = ok
        
    class MembershipChangeResultHandler(EventHandler):
        def __init__(self):
            super().__init__(event_types=[EventType.membership_change_complete,
                                          EventType.membership_change_aborted,])
            
        async def on_event(self, event):
            nonlocal done_by_event
            if event.event_type == EventType.membership_change_complete:
                done_by_event = True
                logger.debug('in handler with success = True\n')
            else:
                logger.debug('in handler with success = False\n')
                done_by_event = False


    # first exchange will tell leader that node 4 needs catchup, by
    # how much from maxIndex in response
    await ts_4.deck.add_event_handler(MembershipChangeResultHandler())
    await ts_4.start_and_join(leader.uri, join_done)

    ts_1.set_trigger(WhenMessageIn(AppendResponseMessage.get_code()))
    ts_4.set_trigger(WhenMessageOut(AppendResponseMessage.get_code()))
    await asyncio.gather(ts_1.run_till_triggers(),
                         ts_4.run_till_triggers())
    ts_1.clear_triggers()
    ts_4.clear_triggers()
    logger.debug("\n\nappend 1 done, should backdown\n\n")
    await ts_1.do_next_in_msg()
    assert ts_1.out_messages[0].code == AppendEntriesMessage.get_code()
    await ts_1.do_next_out_msg()
    assert ts_4.in_messages[0].code == AppendEntriesMessage.get_code()
    await ts_4.do_next_in_msg()
    assert ts_4.out_messages[0].code == AppendResponseMessage.get_code()
    await ts_4.do_next_out_msg()
    # this last exchange was the backdown, should result in replicating record 1, term start
    # next should replicate the command records
    logger.debug("\n\nappend 2 done, backdown should be done, now catchup\n\n")
    await ts_1.do_next_in_msg()
    assert ts_1.out_messages[0].code == AppendEntriesMessage.get_code()
    await ts_1.do_next_out_msg()
    assert ts_4.in_messages[0].code == AppendEntriesMessage.get_code()
    await ts_4.do_next_in_msg()
    assert ts_4.out_messages[0].code == AppendResponseMessage.get_code()

    assert await ts_4.log.get_last_index() == limit
    assert await ts_4.log.get_commit_index() == limit
    assert ts_4.operations.total == limit - 1

    logger.debug("\n\nappend 3 done, node 4 caught up but leader doesn't know yet, faking command to start a round\n")

    async def buy_another_round(last_round_number):
        last_index = await ts_4.log.get_last_index()
        await ts_1.fake_command("add", 1)
        logger.debug(f"\n\nfaked command at leader, should start round {last_round_number} now\n")
        await ts_4.do_next_out_msg()
        await ts_1.do_next_in_msg()
        # these asserts don't test much, but they help readers understand what it happening
        if last_round_number < 10:
            assert ts_1.out_messages[0].code == AppendEntriesMessage.get_code()
            await ts_1.do_next_out_msg()
            assert ts_4.in_messages[0].code == AppendEntriesMessage.get_code()
            await ts_4.do_next_in_msg()
            assert ts_4.out_messages[0].code == AppendResponseMessage.get_code()
        else:
            assert ts_1.out_messages[0].code == MembershipChangeResponseMessage.get_code()
            await ts_1.do_next_out_msg()
            assert ts_4.in_messages[0].code == MembershipChangeResponseMessage.get_code()
            await ts_4.do_next_in_msg()

            
    await cluster.test_trace.start_subtest("Starting a loop of round update and inserted new rounds")
    for i in range(1, 11):
        await buy_another_round(i)
        
    await cluster.test_trace.start_subtest("Leader is about to get another cycle of round complete but records pending, should abort")
    # poised to finish round 9, forcing another round should force abort
    await ts_4.do_next_out_msg()
    
    start_time = time.time()
    while time.time() - start_time < 1 and (done_by_callback is None or done_by_event is None):
        await cluster.deliver_all_pending()
        await asyncio.sleep(0.0001)

    # node 4 should have gotten callback and event to notify it that add failed
    assert done_by_callback is False
    assert done_by_event is False
    
async def test_add_follower_round_2_timeout_1(cluster_maker):
    """
    This is a complicated one. It tests that the leader will timeout while trying to load
    a new node's log prior to adding it to the cluster. Specifically, that it will timeout
    when one election_timeout_max period has passed since the beginning of a loading round
    that is not the first round.

    First an normal election is run with three nodes. Next the node is loaded with a few log
    records, but we cheat and do it directly rather than running the commands for real. This
    reduces the logger output to help with debugging, and it reduces the tracing output.
    Not really necessisary, but nice.

    Next, a new test server is created but not started yet. It has an event handler registered
    for membership change events. The new server gets a call to the start_and_join method of the deck,
    which starts the process of adding the server to the cluster. It sends a message to the leader
    asking to be added, then the leader starts loading it with log records prior to starting the actual
    add.

    We set up pause triggers to capture the moment when the leader sends the append entries message
    that contains the last log entry and pause the leader there, allow the new node to process
    it but not yet send the response.

    If the response message was allowed to proceed, this would be the moment that
    the cluster_ops code would recognized both that the first round of loading is complete, and that
    there are no new log records to send. We want it instead to see new log records and start
    a second round of loading.

    So at this point we use our trick of loading new log records into the log directly. Just one record,
    loaded at nodes 1, 2 and 3.

    Now we disable the network on the new node so that it will not receive the next append entries.

    We let the paused pending entries response proceed, so that the cluster_ops code starts a new
    round of loading and starts a timeout function that will detect if the round takes longer than
    election_timeout_max to complete. Since we are not allowing the new node to receive messages,
    this timeout will fire and cause the add node abort sequence to run.

    The leader will reset all the internal state that it maintains for loading a node before
    add to the cluster, and it will send a response to the original memebership change message
    indicating that it failed.

    When node 4 receives this message, it will call our callback and issue our expected event,
    in both cases indicating failure, which we check.

    At this point everyone has forgotten that the add has been attempted, so another attempt
    is possbile.

    So, we call stop on the new node, call the start_and_join method again and enable the network.
    The leader should start a new loading operation, which should succeed, then notify all the
    followers (not the new node) that they should add the new node, then once it gets commit
    concurrence it will complete the add operation and send a membership change response to node 4
    which will trigger our callback and event handler.

    As a result of the add completion, the leader will update its commit index and the other
    servers need to know about it in order to send make the membership change permanent. So
    we trigger it to send a heartbeat, and then check all the followers to ensure the
    cluster state is correct..

    Simple!
    
    """
    
    cluster = cluster_maker(3)
    config = cluster.build_cluster_config(heartbeat_period=0.005,
                                          election_timeout_min=0.01,
                                          election_timeout_max=0.011,
                                          use_pre_vote=False)
    cluster.set_configs(config)

    await cluster.test_trace.define_test("Testing timeout during second round of follower log loading", logger=logger)
    await cluster.test_trace.start_test_prep("Normal election")
    await cluster.start()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]

    await ts_1.start_campaign()
    await cluster.run_election()

    msg_per = await ts_1.deck.get_max_entries_per_message()
    limit = int(msg_per/2) + 2 # get just one block to update, index starts at two because of term start log entry
    await cluster.test_trace.start_subtest(f"Node 1 is leader, cheat loading {limit-1} log records")
    for i in range(2, limit+1):
        for ts in [ts_1, ts_2, ts_3]:
            await ts.fake_command("add", 1)
    for ts in [ts_1, ts_2, ts_3]:
        assert await ts.log.get_last_term() == 1
        assert await ts.log.get_last_index() == limit
        assert await ts.log.get_commit_index() == limit
        assert await ts.log.get_applied_index() == limit
        assert ts.operations.total == limit - 1

    await ts_1.disable_timers()
    await ts_2.disable_timers()
    await ts_3.disable_timers()
    ts_4 = await cluster.add_node()
    await ts_4.disable_timers()
    leader = cluster.get_leader()
    done_by_callback = None
    done_by_event = None
    async def join_done(ok, new_uri):
        nonlocal done_by_callback
        logger.debug(f"\nJoin callback said {ok} joining as {new_uri}\n")
        done_by_callback = ok
        
    class MembershipChangeResultHandler(EventHandler):
        def __init__(self):
            super().__init__(event_types=[EventType.membership_change_complete,
                                          EventType.membership_change_aborted,])
            
        async def on_event(self, event):
            nonlocal done_by_event
            if event.event_type == EventType.membership_change_complete:
                done_by_event = True
                logger.debug('in handler with success = True\n')
            else:
                logger.debug('in handler with success = False\n')
                done_by_event = False

    # first exchange will tell leader that node 4 needs catchup, by
    # how much from maxIndex in response
    await ts_4.deck.add_event_handler(MembershipChangeResultHandler())
    await cluster.test_trace.start_subtest("Node 4 created, telling it to start_and_join, waiting for append entries sequences")
    await ts_4.start_and_join(leader.uri, join_done, timeout=100.0)

    ts_1.set_trigger(WhenMessageIn(AppendResponseMessage.get_code()))
    ts_4.set_trigger(WhenMessageOut(AppendResponseMessage.get_code()))
    await asyncio.gather(ts_1.run_till_triggers(),
                         ts_4.run_till_triggers())
    ts_1.clear_triggers()
    ts_4.clear_triggers()
    logger.debug("\n\nappend 1 done, should backdown\n\n")
    await ts_1.do_next_in_msg()
    assert ts_1.out_messages[0].code == AppendEntriesMessage.get_code()
    await ts_1.do_next_out_msg()
    assert ts_4.in_messages[0].code == AppendEntriesMessage.get_code()
    await ts_4.do_next_in_msg()
    assert ts_4.out_messages[0].code == AppendResponseMessage.get_code()
    await ts_4.do_next_out_msg()
    # this last exchange was the backdown, should result in replicating record 1, term start
    # next should replicate the command records
    logger.debug("\n\nappend 2 done, backdown should be done, now catchup\n\n")
    await ts_1.do_next_in_msg()
    assert ts_1.out_messages[0].code == AppendEntriesMessage.get_code()
    await ts_1.do_next_out_msg()
    assert ts_4.in_messages[0].code == AppendEntriesMessage.get_code()
    await ts_4.do_next_in_msg()
    assert ts_4.out_messages[0].code == AppendResponseMessage.get_code()
    await ts_4.do_next_out_msg()

    assert await ts_4.log.get_last_index() == limit
    assert await ts_4.log.get_commit_index() == limit
    assert ts_4.operations.total == limit - 1

    logger.debug("\n\nappend 3 done, node 4 caught up but leader doesn't know yet, faking command\n")
    await cluster.test_trace.start_subtest("Node 4 has caught up its log, but last append response is paused before delivery to leader, adding log record")
    await ts_1.fake_command("add", 1)
    await ts_2.fake_command("add", 1)
    await ts_3.fake_command("add", 1)
    logger.debug("\n\nfaked command at leader, should start round 2 now, but blocking node 4 so timeout should happen\n")

    # let leader run until timeout causes send of member change response, but don't let it deliver
    await cluster.test_trace.start_subtest("Blocking comms at node 4, running network ops and Waiting for leader to timeout and notify node 4")
    ts_1.set_trigger(WhenMessageOut(MembershipChangeResponseMessage.get_code(), flush_when_done=False))
    ts_4.block_network()
    await ts_1.run_till_triggers()
    ts_1.clear_triggers()
    
    assert ts_1.out_messages[0].ok == False
    # the network sim will discard any messages that were missed, so node 4 will not see the last append entries
    ts_4.unblock_network()

    start_time = time.time()
    while time.time() - start_time < 1 and (done_by_callback is None or done_by_event is None):
        await cluster.deliver_all_pending()
        await asyncio.sleep(0.0001)

    assert ts_4.operations.total != ts_1.operations.total
    # node 4 should have gotten callback and event to notify it that add failed
    assert done_by_callback is False
    assert done_by_event is False

    # cluster config should be back to original state, nothing pending
    cc = await ts_1.deck.cluster_ops.get_cluster_config()
    assert ts_4.uri not in cc.nodes
    assert cc.pending_node is None
    await cluster.test_trace.start_subtest("Node 4 callback and handler results correct and cluster node list state correct, restarting add with all normal")

    # trying to add node again should work
    await ts_4.tmp_stop()
    done_by_callback = None
    done_by_event = None
    ts_2.unblock_network()
    ts_3.unblock_network()
    await ts_4.start_and_join(leader.uri, join_done, timeout=1)
    
    start_time = time.time()
    while time.time() - start_time < 1 and (done_by_callback is None or done_by_event is None):
        await cluster.deliver_all_pending()
        await asyncio.sleep(0.0001)

    assert ts_4.operations.total == ts_1.operations.total
    assert done_by_callback is True
    assert done_by_event is True

    start_time = time.time()
    while time.time() - start_time < 1:
        await cluster.deliver_all_pending()
        await asyncio.sleep(0.0001)
        cc = await ts_1.deck.cluster_ops.get_cluster_config()
        if ts_4.uri in cc.nodes:
            break
    assert ts_4.uri in cc.nodes
    assert cc.pending_node is None

    await ts_1.send_heartbeats()
    await cluster.deliver_all_pending()

    for ts in [ts_2, ts_3, ts_4]:
        cc = await ts.deck.cluster_ops.get_cluster_config()
        assert ts_4.uri in cc.nodes
        assert cc.pending_node is None

async def test_reverse_add_follower_1(cluster_maker):
    """
    This tests the scenario where a node begins the process of joining the cluster but 
    a crash of the leader at a specific time leaves the leader with a log record describing
    the membership change, but no other node also having that record. Then an election is run
    and the new leader writes a term start record in the log which ends up with the same
    record index as the old leader's change membership record. So once the old leader restarts
    and resynchronizes it overwrites the member change record and reverses its effect, so it
    no longer thinks the other node is joining. The node that was trying to join will experience
    a timeout on that request.
    
    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """
    
    cluster = cluster_maker(3)
    config = cluster.build_cluster_config(use_pre_vote=False)
    cluster.set_configs(config)

    await cluster.test_trace.define_test("Testing reversal of follower addition due to leader crash", logger=logger)
    await cluster.test_trace.start_test_prep("Normal election")
    await cluster.start()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]

    await ts_1.start_campaign()
    await cluster.run_election()
    await cluster.test_trace.start_subtest("Node 1 is leader, running a command then adding node 4 and starting the join")
    
    command_result = await cluster.run_command("add 1", 1)
    assert ts_1.operations.total == 1
    assert ts_2.operations.total == 1
    assert ts_3.operations.total == 1
    ts_4 = await cluster.add_node()
    leader = cluster.get_leader()
    await ts_4.start_and_join(leader.uri)
    assert ts_4.deck.join_waiter_handle is not None
    

    # want add load to complete and leader to send add log message, but we don't want followers
    # to accept that message, rather to discard it.
    ts_1.set_trigger(WhenMessageIn(MembershipChangeMessage.get_code()))
    ts_4.set_trigger(WhenMessageOut(MembershipChangeMessage.get_code()))
    await asyncio.gather(ts_1.run_till_triggers(),
                         ts_4.run_till_triggers())
    ts_1.clear_triggers()
    ts_4.clear_triggers()

    # first dialog should have false from new node
    ts_1.set_trigger(WhenMessageIn(AppendResponseMessage.get_code()))
    ts_4.set_trigger(WhenMessageOut(AppendResponseMessage.get_code()))
    await asyncio.gather(ts_1.run_till_triggers(),
                         ts_4.run_till_triggers())
    ts_1.clear_triggers()
    ts_4.clear_triggers()
    logger.debug(f"\n\n{ts_1.in_messages[0]}\n\n")
    assert not ts_1.in_messages[0].success
    await ts_1.do_next_in_msg()

    
    # second dialog should have ok from new node, but one more needed
    ts_1.set_trigger(WhenMessageIn(AppendResponseMessage.get_code()))
    ts_4.set_trigger(WhenMessageOut(AppendResponseMessage.get_code()))
    await asyncio.gather(ts_1.run_till_triggers(),
                         ts_4.run_till_triggers())
    ts_1.clear_triggers()
    ts_4.clear_triggers()
    logger.debug(f"\n\n{ts_1.in_messages[0]}\n\n")
    assert ts_1.in_messages[0].success
    assert ts_1.in_messages[0].success
    assert ts_1.in_messages[0].maxIndex == 1
    await ts_1.do_next_in_msg()
    # second dialog should have ok from new node, but one more needed
    ts_1.set_trigger(WhenMessageIn(AppendResponseMessage.get_code()))
    ts_4.set_trigger(WhenMessageOut(AppendResponseMessage.get_code()))
    await asyncio.gather(ts_1.run_till_triggers(),
                         ts_4.run_till_triggers())
    ts_1.clear_triggers()
    ts_4.clear_triggers()
    logger.debug(f"\n\n{ts_1.in_messages[0]}\n\n")
    assert ts_1.in_messages[0].success
    assert ts_1.in_messages[0].maxIndex == 2

    # next message from leader should be log record with membership change, or it might
    # be the response to the adding node
    await ts_1.do_next_in_msg()
    for index,msg in enumerate(ts_1.out_messages):
        if msg.code == AppendEntriesMessage.get_code():
            log_rec = msg.entries[0]
            assert log_rec.code == RecordCode.cluster_config
        if msg.code == MembershipChangeResponseMessage.get_code():
            ts_4.in_messages.append(msg)
            await ts_4.do_next_in_msg()
    # 
    assert await ts_1.log.get_last_index() > await ts_2.log.get_last_index()
    assert await ts_1.log.get_last_index() > await ts_3.log.get_last_index()
    await cluster.test_trace.start_subtest("Node 4 up to date and leader saved membership change log record, crashing leader and running election")

    await ts_1.simulate_crash()
    await ts_2.start_campaign(authorized=True)
    sequence = SPartialElection(cluster, [ts_2.uri, ts_3.uri], 1)
    await cluster.run_sequence(sequence)

    # ensure that the new term start log message is the same index as the
    # cluster change log message at the old leader, and a different term
    assert await ts_1.log.get_last_index() == await ts_2.log.get_last_index()
    assert await ts_1.log.get_last_index() == await ts_3.log.get_last_index()
    assert await ts_1.log.get_last_term() != await ts_2.log.get_last_term()
    assert await ts_1.log.get_last_term() != await ts_3.log.get_last_term()

    # now restart the old leader, send a heart beat from new leader, hold old leader before
    # processing message, check to see that it has temporary add (restored from log). Then
    # let it process message and make sure it discards add.
    await cluster.test_trace.start_subtest("Node 2 is now leader, restarting crashed old leader and sending heartbeats")
    await ts_1.recover_from_crash()
    await ts_2.send_heartbeats(target_only=ts_1.uri)
    ts_1.set_trigger(WhenMessageIn(AppendEntriesMessage.get_code()))
    ts_2.set_trigger(WhenMessageOut(AppendEntriesMessage.get_code()))
    await asyncio.gather(ts_1.run_till_triggers(),
                         ts_2.run_till_triggers())
    ts_1.clear_triggers()
    ts_2.clear_triggers()
    cc = await ts_1.get_cluster_config()
    assert cc.pending_node is not None
    logger.debug(f'\n\nprocessing message {ts_1.in_messages[0]}\n\n')
    # this should note out of sync
    await ts_1.do_next_in_msg()
    assert not ts_1.out_messages[0].success
    await ts_1.do_next_out_msg()
    await ts_2.do_next_in_msg()
    await ts_2.do_next_out_msg()
    await ts_1.do_next_in_msg()
    assert ts_1.out_messages[0].success
    
    cc = await ts_1.get_cluster_config()
    assert cc.pending_node is None
    # now stop ts_4 cause it never gets notified
    await ts_4.stop()

async def reverse_remove_part_1(cluster, timeout, callback, event_handler):

    await cluster.start()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]

    await ts_1.start_campaign()
    await cluster.run_election()
    await cluster.test_trace.start_subtest("Node 1 is leader, running a command, then starting cluster exit at node 3")
    
    command_result = await cluster.run_command("add 1", 1)
    assert ts_1.operations.total == 1
    assert ts_2.operations.total == 1
    assert ts_3.operations.total == 1

    await ts_3.deck.add_event_handler(event_handler)
    await ts_3.exit_cluster(callback, timeout)
    ts_1.set_trigger(WhenMessageIn(MembershipChangeMessage.get_code()))
    ts_3.set_trigger(WhenMessageOut(MembershipChangeMessage.get_code()))
    await asyncio.gather(ts_1.run_till_triggers(),
                         ts_3.run_till_triggers())
    ts_1.clear_triggers()
    ts_3.clear_triggers()
    # next message from leader should be log record with membership change
    await ts_1.do_next_in_msg()
    # messages are sent with create_task, so give it a chance to run
    await asyncio.sleep(0.0)
    assert ts_1.out_messages[0].code == AppendEntriesMessage.get_code()
    log_rec = ts_1.out_messages[0].entries[0]
    assert log_rec.code == RecordCode.cluster_config
    # 
    assert await ts_1.log.get_last_index() > await ts_2.log.get_last_index()
    assert await ts_1.log.get_last_index() > await ts_3.log.get_last_index()

    # now crash the leader, no changes at followers yet, so leader's record
    # should get overwritten on restart
    await cluster.test_trace.start_subtest("Leader has saved membership change log but not replicated it, crashing leader and running election")
    await ts_1.simulate_crash()
    await ts_2.start_campaign(authorized=True)
    sequence = SPartialElection(cluster, [ts_2.uri, ts_3.uri], 1)
    await cluster.run_sequence(sequence)

    # ensure that the new term start log message is the same index as the
    # member change log message at the old leader, and a different term
    assert await ts_1.log.get_last_index() == await ts_2.log.get_last_index()
    assert await ts_1.log.get_last_index() == await ts_3.log.get_last_index()
    assert await ts_1.log.get_last_term() != await ts_2.log.get_last_term()
    assert await ts_1.log.get_last_term() != await ts_3.log.get_last_term()

    # now restart the old leader, send a heart beat from new leader, hold old leader before
    # processing message, check to see that it has temporary add (restored from log). Then
    # let it process message and make sure it discards add.
    await cluster.test_trace.start_subtest("Log state verified, restarting crashed lerader and sending heartbeats from new leader")
    await ts_1.recover_from_crash()
    await ts_2.send_heartbeats(target_only=ts_1.uri)
    ts_1.set_trigger(WhenMessageIn(AppendEntriesMessage.get_code()))
    ts_2.set_trigger(WhenMessageOut(AppendEntriesMessage.get_code()))
    await asyncio.gather(ts_1.run_till_triggers(),
                         ts_2.run_till_triggers())
    ts_1.clear_triggers()
    ts_2.clear_triggers()
    cc = await ts_1.get_cluster_config()
    assert cc.pending_node is not None
    logger.debug(f'\n\nprocessing message {ts_1.in_messages[0]}\n\n')
    # this should note out of sync
    await ts_1.do_next_in_msg()
    assert not ts_1.out_messages[0].success
    msg = await ts_1.do_next_out_msg()
    logger.debug(f'\nout from ts1 {msg}\n')
    if msg.code == 'append_entries' and len(msg.entries) > 0:
        logger.debug(f'{msg.entries[0].code}')
        
    msg = await ts_2.do_next_in_msg()
    logger.debug(f'\nin at ts2 {msg}\n')
    if msg.code == 'append_entries' and len(msg.entries) > 0:
        logger.debug(f'{msg.entries[0].code}')
    msg = await ts_2.do_next_out_msg()
    logger.debug(f'\nout from ts2 {msg}\n')
    if msg.code == 'append_entries' and len(msg.entries) > 0:
        logger.debug(f'{msg.entries[0].code}')
    msg = await ts_1.do_next_in_msg()
    logger.debug(f'\nin at ts1 {msg}\n')
    if msg.code == 'append_entries' and len(msg.entries) > 0:
        logger.debug(f'{msg.entries[0].code}')
    msg = await ts_1.do_next_out_msg()
    logger.debug(f'\nout from ts1 {msg}\n')
    if msg.code == 'append_entries' and len(msg.entries) > 0:
        logger.debug(f'{msg.entries[0].code}')
    await asyncio.sleep(0)
    cc = await ts_1.get_cluster_config()
    assert cc.pending_node is None
    await cluster.test_trace.start_subtest("Old leader cluster membership as original confirmed, running final checks")

async def test_reverse_remove_follower_1(cluster_maker):
    """
    This tests the scenario where a node begins the process of exiting the cluster's membership
    list but a crash of the leader at a specific time leaves the leader with a log record describing
    the membership change, but no other node also having that record. Then and election is run
    and the new leader writes a term start record in the log which ends up with the same
    record index as the old leader's change membership record. So once the old leader restarts
    and resynchronizes it overwrites the member change record and reverses its effect, so it
    no longer thinks the other node is exiting. The node that was trying to exit will experience
    a timeout on that request.
    
    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.

    """
    
    cluster = cluster_maker(3)
    config = cluster.build_cluster_config(use_pre_vote=False)
    cluster.set_configs(config)
    await cluster.test_trace.define_test("Testing reversal of follower removal due to leader crash with timeout", logger=logger)
    await cluster.test_trace.start_test_prep("Normal election")

    done_by_callback = None
    done_by_event = None
    async def exit_done(ok, exit_uri):
        nonlocal done_by_callback 

        logger.debug(f"Exit callback said {ok} on exiting request")
        done_by_callback = ok

    class MembershipChangeResultHandler(EventHandler):
        def __init__(self):
            super().__init__(event_types=[EventType.membership_change_complete,
                                          EventType.membership_change_aborted,])
            
        async def on_event(self, event):
            nonlocal done_by_event
            if event.event_type == EventType.membership_change_complete:
                done_by_event = True
                logger.debug('in handler with success = True\n')
            else:
                logger.debug('in handler with success = False\n')
                done_by_event = False

    await reverse_remove_part_1(cluster, 0.02, exit_done, MembershipChangeResultHandler())

    start_time = time.time()
    while time.time() - start_time < 0.05 and done_by_callback is None:
        await cluster.deliver_all_pending()
        await asyncio.sleep(0.001)
    assert done_by_callback is False
    await asyncio.sleep(0.00)
    assert done_by_event is False

async def test_reverse_remove_follower_2(cluster_maker):
    """
    This tests is identical to test_reverse_remove_follower_1 except that the cluster exiting node told
    to stop before it can receive the timeout. This tests code that cleans up the handler in
    deck.py that monitors the cluster exit process. It is a very unlikely event in real life, but possible
    
    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.

    """
    
    cluster = cluster_maker(3)
    config = cluster.build_cluster_config(use_pre_vote=False)
    cluster.set_configs(config)
    await cluster.test_trace.define_test("Testing reversal of follower removal due to leader crash with stop before timeout", logger=logger)
    await cluster.test_trace.start_test_prep("Normal election")

    done_by_callback = None
    done_by_event = None
    async def exit_done(ok, exit_uri):
        nonlocal done_by_callback 

        logger.debug(f"Exit callback said {ok} on exiting request")
        done_by_callback = ok

    class MembershipChangeResultHandler(EventHandler):
        def __init__(self):
            super().__init__(event_types=[EventType.membership_change_complete,
                                          EventType.membership_change_aborted,])
            
        async def on_event(self, event):
            nonlocal done_by_event
            if event.event_type == EventType.membership_change_complete:
                done_by_event = True
                logger.debug('in handler with success = True\n')
            else:
                logger.debug('in handler with success = False\n')
                done_by_event = False

    await reverse_remove_part_1(cluster, 0.1, exit_done, MembershipChangeResultHandler())
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]
    await ts_3.stop()
    
async def test_reverse_remove_follower_3(cluster_maker):
    """
    This test is tricky to setup. The targeted condition is that a node tries to exit the cluster, and it
    has received the membership change log record, but it has not yet been committed, then it
    is told to remove the record because it is superceeded by the same index at a later term.
    At this point it should reverse the exit and remain in the cluster.

    To make this happen, we start with a five node cluster. We run election, run a command, then start
    node 5 down the exit path. When the leader has recorded the change in the log and is ready to
    send it out for replication we partion the network so that the leader and the exiting node are
    together on a minority network. We allow the exiting node to get the append entries record and
    apply it, but the leader can't get a commit because the other nodes are unreachable. So both
    leader and node 5 have applied and saved the removal of node 5. The record index will be 3 and the term
    will be 1.

    At this point we trigger node 2 to run a new election which it will win, saving a TERM START record
    at index 3 and term 2.

    Now the network will be healed, and the new leader will be triggered to send heartbeats. This will
    result in the two minority nodes realizing that their last log records are invalid because of the
    new term in the heartbeat spec for last log record term. This will cause and overwrite and
    a reversal of the cluster membership change.
    
    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.

    """
    
    cluster = cluster_maker(5)
    config = cluster.build_cluster_config(use_pre_vote=False)
    cluster.set_configs(config)
    await cluster.test_trace.define_test("Testing reversal of follower removal due to network partition and election", logger=logger)
    await cluster.test_trace.start_test_prep("Normal election")

    await cluster.start()
    uri_1, uri_2, uri_3, uri_4, uri_5 = cluster.node_uris
    ts_1, ts_2, ts_3, ts_4, ts_5 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3, uri_4, uri_5]]

    await ts_1.start_campaign()
    await cluster.run_election()
    await cluster.test_trace.start_subtest("Node 1 is leader, running a command, then starting cluster exit at node 5")
    
    command_result = await cluster.run_command("add 1", 1)
    assert ts_1.operations.total == 1
    assert ts_2.operations.total == 1
    assert ts_3.operations.total == 1
    assert ts_4.operations.total == 1
    assert ts_5.operations.total == 1

    await ts_5.exit_cluster(timeout=0.05)
    ts_1.set_trigger(WhenMessageIn(MembershipChangeMessage.get_code()))
    ts_5.set_trigger(WhenMessageOut(MembershipChangeMessage.get_code()))
    await asyncio.gather(ts_1.run_till_triggers(),
                         ts_5.run_till_triggers())
    ts_1.clear_triggers()
    ts_5.clear_triggers()
    # next message from leader should be log record with membership change
    await ts_1.do_next_in_msg()
    # messages are sent with create_task, so give it a chance to run
    await asyncio.sleep(0.0)
    assert ts_1.out_messages[0].code == AppendEntriesMessage.get_code()
    log_rec = ts_1.out_messages[0].entries[0]
    assert log_rec.code == RecordCode.cluster_config
    # 
    assert await ts_1.log.get_last_index() > await ts_2.log.get_last_index()
    assert await ts_1.log.get_last_index() > await ts_3.log.get_last_index()
    assert await ts_1.log.get_last_index() > await ts_4.log.get_last_index()
    assert await ts_1.log.get_last_index() > await ts_5.log.get_last_index()

    await cluster.test_trace.start_subtest("Leader has saved member change log record, splitting network, delivering pending, starting election")
    part1 = {uri_1: ts_1, uri_5: ts_5}
    part2 = {uri_2: ts_2,
             uri_3: ts_3,
             uri_4: ts_4}
    await cluster.split_network([part1, part2])
    maj = cluster.net_mgr.get_majority_network()
    
    minor = cluster.net_mgr.get_minority_networks()[0]
    await ts_1.do_next_out_msg()
    await ts_1.do_next_out_msg()
    await ts_1.do_next_out_msg()
    await ts_1.do_next_out_msg()
    await minor.deliver_all_pending()
    assert await ts_1.log.get_last_index() == await ts_5.log.get_last_index()
    
    await ts_2.start_campaign(authorized=True)
    sequence = SPartialElection(cluster, [ts_2.uri, ts_3.uri, ts_4.uri], 1)
    await cluster.run_sequence(sequence)

    # ensure that the new term start log message is the same index as the
    # member change log message at the old leader, and a different term
    assert await ts_1.log.get_last_index() == await ts_2.log.get_last_index()
    assert await ts_1.log.get_last_index() == await ts_3.log.get_last_index()
    assert await ts_1.log.get_last_index() == await ts_4.log.get_last_index()
    assert await ts_1.log.get_last_term() != await ts_2.log.get_last_term()
    assert await ts_1.log.get_last_term() != await ts_3.log.get_last_term()
    assert await ts_1.log.get_last_term() != await ts_4.log.get_last_term()

    # now heal network, send a heart beat from new leader, let things run until settled and check conditions
    await cluster.test_trace.start_subtest("Log state verified, healing partition and triggering heartbeats")
    await cluster.unsplit()
    await ts_2.send_heartbeats()
    await cluster.deliver_all_pending()
    cc_1 = await ts_1.get_cluster_config()
    assert cc_1.pending_node is None
    cc_5 = await ts_1.get_cluster_config()
    assert cc_5.pending_node is None
    
async def test_add_follower_timeout_1(cluster_maker):
    """
    Simple test of add follower timeout, just prevent the leader from acting on the request.
    
    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """
    
    cluster = cluster_maker(3)
    config = cluster.build_cluster_config(heartbeat_period=0.05,
                                          election_timeout_min=0.1,
                                          election_timeout_max=0.11,
                                          use_pre_vote=False)
    cluster.set_configs(config)

    await cluster.test_trace.define_test("Starting election at node 1 of 3", logger=logger)
    await cluster.test_trace.start_test_prep("Normal election")
    await cluster.start()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]

    await ts_1.start_campaign()
    await cluster.run_election()
    await cluster.test_trace.start_subtest("Node 1 is leader, starting node 4 join but setting timeout low and sisabling messages")
    
    ts_4 = await cluster.add_node()
    leader = cluster.get_leader()
    assert leader.get_role().role_name == "LEADER"
    callback_result = None
    async def join_done(ok, new_uri):
        nonlocal callback_result
        logger.debug(f"Join callback said {ok} joining as {new_uri}")
        callback_result = ok

    assert await ts_1.deck.get_election_timeout() > 0.01
    assert await ts_1.deck.get_heartbeat_period() > 0.01
    assert (await ts_1.deck.get_election_timeout_range())[1] > 0.01
    
    await ts_4.start_and_join(leader.uri, join_done, timeout=0.01)
    ts_1.block_network()
    start_time = time.time()
    while time.time() - start_time < 0.05 and callback_result is None:
        await cluster.deliver_all_pending()
        await asyncio.sleep(0.001)

    assert callback_result == False

async def test_add_follower_errors_1(cluster_maker):
    """
    Testing a couple of error conditions for adding follower, one where the specified leader is
    bogus, one where the specified leader is actually a follower.

    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """
    
    cluster = cluster_maker(3)
    config = cluster.build_cluster_config(heartbeat_period=0.05,
                                          election_timeout_min=0.1,
                                          election_timeout_max=0.11,
                                          use_pre_vote=False)
    cluster.set_configs(config)

    await cluster.test_trace.define_test("Starting election at node 1 of 3", logger=logger)
    await cluster.test_trace.start_test_prep("Normal election")
                                  
    await cluster.start()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]

    await ts_1.start_campaign()
    await cluster.run_election()
    await cluster.test_trace.start_subtest("Node 1 is leader, sending heartbeat so replies will tell us that followers did commit")
    
    ts_4 = await cluster.add_node()
    leader = cluster.get_leader()
    assert leader.get_role().role_name == "LEADER"
    callback_result = None
    async def join_done(ok, new_uri):
        nonlocal callback_result
        logger.debug(f"Join callback said {ok} joining as {new_uri}")
        callback_result = ok

    # bogus leader id should raise
    with pytest.raises(Exception):
        await ts_4.start_and_join('xxx', join_done, timeout=0.01)

    # Trying to join at non-leader should get error response
    await ts_4.start_and_join(ts_2.uri, join_done, timeout=0.1)
    start_time = time.time()
    while time.time() - start_time < 0.05 and callback_result is None:
        await cluster.deliver_all_pending()
        await asyncio.sleep(0.001)

    assert callback_result == False

async def test_remove_candidate_1(cluster_maker):
    """
    Test that a node can remove itself from the cluster when it is in candidate role.
    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    
    """
    
    cluster = cluster_maker(3)
    config = cluster.build_cluster_config()

    cluster.set_configs(config)

    await cluster.test_trace.define_test("Starting election at node 1 of 3", logger=logger)
    await cluster.test_trace.start_test_prep("Normal election")
    await cluster.start()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]

    await ts_1.start_campaign()
    await cluster.run_election()
    await cluster.test_trace.start_subtest("Node 1 is leader, telling node 3 to become a candidate and then immediately start exiting")
    
    #ts_4 = await cluster.add_node()
    leader = cluster.get_leader()
    assert leader.get_role().role_name == "LEADER"

    # remove node while it is a candidate
    await ts_3.start_campaign()
    await ts_3.exit_cluster()
    await cluster.deliver_all_pending()
    await ts_1.send_heartbeats()
    await cluster.deliver_all_pending()
    assert ts_3.deck.role.stopped

    # now make sure heartbeat send only goes to the one remaining follower
    await ts_1.send_heartbeats()
    assert len(ts_1.out_messages) == 1
    assert ts_1.out_messages[0].receiver == ts_2.uri

async def test_update_settings(cluster_maker):
    """
    Basic test of updating cluster wide settings.
    
    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """
    
    cluster = cluster_maker(3)
    config = cluster.build_cluster_config(use_pre_vote=False)
    cluster.set_configs(config)

    await cluster.test_trace.define_test("Starting election at node 1 of 3", logger=logger)
    await cluster.test_trace.start_test_prep("Normal election")
    await cluster.start()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]

    await ts_1.start_campaign()
    await cluster.run_election()
    await ts_1.send_heartbeats()
    await cluster.deliver_all_pending()
    await cluster.test_trace.start_subtest("Node 1 is leader, sending settings update")

    orig_cc = await ts_1.deck.get_cluster_config()
    cur_settings = orig_cc.settings
    orig_value = cur_settings.max_entries_per_message
    new_settings = ClusterSettings(**cur_settings.__dict__)
    new_settings.max_entries_per_message += 1

    with pytest.raises(Exception):
        await ts_2.deck.update_settings(new_settings)
        
    await ts_1.deck.update_settings(new_settings)
    start_time = time.time()
    while time.time() - start_time < 0.1 and cur_settings.max_entries_per_message == orig_value:
        await cluster.deliver_all_pending()
        await asyncio.sleep(0.001)
        new_cc = await ts_1.deck.get_cluster_config()
        cur_settings = new_cc.settings
    assert (await ts_1.deck.get_cluster_config()).settings.max_entries_per_message != orig_value

    await ts_1.send_heartbeats()
    new_cc = await ts_2.deck.get_cluster_config()
    cur_settings = new_cc.settings
    start_time = time.time()
    while time.time() - start_time < 0.1 and cur_settings.max_entries_per_message == orig_value:
        await cluster.deliver_all_pending()
        await asyncio.sleep(0.001)
        new_cc = await ts_2.deck.get_cluster_config()
        cur_settings = new_cc.settings
    assert (await ts_2.deck.get_cluster_config()).settings.max_entries_per_message != orig_value
    assert (await ts_3.deck.get_cluster_config()).settings.max_entries_per_message != orig_value
