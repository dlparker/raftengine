#!/usr/bin/env python
import asyncio
import logging
import pytest
import time
from pathlib import Path
from raftengine.api.events import EventType, EventHandler
from raftengine.messages.request_vote import RequestVoteMessage,RequestVoteResponseMessage
from raftengine.messages.append_entries import AppendEntriesMessage, AppendResponseMessage
from dev_tools.sequences import SNormalElection, SNormalCommand, SPartialElection, SPartialCommand
from dev_tools.logging_ops import setup_logging
from dev_tools.triggers import WhenElectionDone
from dev_tools.pausing_cluster import PausingCluster, cluster_maker

#extra_logging = [dict(name=__name__, level="debug"),]
#setup_logging(extra_logging)
default_level='error'
default_level='debug'
setup_logging(default_level=default_level)
logger = logging.getLogger("test_code")

        
async def test_event_handlers(cluster_maker):
    
    cluster = cluster_maker(3)
    cluster.set_configs()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]
    logger = logging.getLogger("test_code")

    role_change_counter = 0
    term_change_counter = 0
    leader_uri = None
    election_op_counter = 0
    resync_op_counter = 0
    election_saves = []
    resync_saves = []
    class RoleChangeHandler(EventHandler):
        def __init__(self):
            super().__init__(event_types=[EventType.role_change,])
            
        async def on_event(self, event):
            nonlocal role_change_counter
            role_change_counter += 1
            # make sure to_json does not blow up
            event.to_json()
            
    class TermChangeHandler(EventHandler):
        def __init__(self):
            super().__init__(event_types=[EventType.term_change,])
            
        async def on_event(self, event):
            nonlocal term_change_counter
            term_change_counter += 1
            # make sure to_json does not blow up
            event.to_json()

    class LeaderChangeHandler(EventHandler):
        def __init__(self):
            super().__init__(event_types=[EventType.leader_change,])
            
        async def on_event(self, event):
            nonlocal leader_uri
            leader_uri = event.new_leader
            event.to_json()

    class ElectionHandler(EventHandler):
        def __init__(self, ts):
            super().__init__(event_types=[EventType.election_op,])
            self.ts = ts
            
        async def on_event(self, event):
            nonlocal election_op_counter
            nonlocal election_saves 
            election_op_counter += 1
            event.to_json()
            election_saves.append(event.op)
            assert "ELECTION_OP"  == str(event.event_type)
            
    class ResyncHandler(EventHandler):
        def __init__(self, ts):
            super().__init__(event_types=[EventType.resync_op,])
            self.ts = ts
            
        async def on_event(self, event):
            nonlocal resync_op_counter
            nonlocal resync_saves 
            resync_op_counter += 1
            event.to_json()
            resync_saves.append(event.op)

    rch_by_node = {}
    for ts in [ts_1, ts_2, ts_3]:
        rch = RoleChangeHandler()
        rch_by_node[ts.uri] = rch
        await ts.hull.add_event_handler(rch)
        await ts.hull.add_event_handler(TermChangeHandler())
        leader_handler = LeaderChangeHandler()
        await ts.hull.add_event_handler(leader_handler)
        election_handler = ElectionHandler(ts)
        await ts.hull.add_event_handler(election_handler)
        resync_handler = ResyncHandler(ts)
        await ts.hull.add_event_handler(resync_handler)

    await cluster.start()
    await ts_1.start_campaign()
    await cluster.run_election()
    assert cluster.get_leader() == ts_1
    # each node should change to follower at start, thats 3
    # then ts_1 should change to candidate, then leader, thats 5
    assert role_change_counter == 5 # once to candidate, once to leader
    assert term_change_counter == 3 # once for each node

    expecting = ['START_PRE_ELECTION', 'PRE_WON', 'START_ELECTION', 'NEWER_TERM', 'NEWER_TERM', 'BROADCASTING_TERM_START',
                 'WON', 'JOINED_LEADER', 'JOINED_LEADER']
    for index, item in enumerate(expecting):
        assert item == election_saves[index]
    assert election_op_counter == len(expecting)


    # no block a follower while we run a couple of commands
    ts_2.block_network()
    command_result = await cluster.run_command("add 1", 1)
    command_result = await cluster.run_command("add 1", 1)
    ts_2.unblock_network()
    await ts_1.send_heartbeats(target_only=ts_2.uri)
    await cluster.deliver_all_pending()

    await asyncio.sleep(0)
    
    r_expecting = ['SENDING_BACKDOWN', 'SENDING_CATCHUP']
    for index, item in enumerate(r_expecting):
        assert item == resync_saves[index]
    assert resync_op_counter == len(r_expecting)
    
    for ts in [ts_2, ts_3]:
        rch = rch_by_node[ts.uri]
        await ts.hull.remove_event_handler(rch)
        
    # now demote the leader and make sure we get only one event
    await ts_1.hull.demote_and_handle()
    await asyncio.sleep(0)
    assert role_change_counter == 6
    await cluster.stop_auto_comms()


async def test_message_errors(cluster_maker):
    """
    This test uses error insertion to make things that normally don't blow up do so. Code that
    gets run a million times with no problem, but that has the potential to blow up if something
    funky like memory corruption happens. We have code to catch these cases, so there needs
    to be code to test that the catches work.

    Starts with a normal election, then inserts two errors into the message processing code.
    
    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """
    cluster = cluster_maker(3)
    config = cluster.build_cluster_config()
    cluster.set_configs(config)
    uri_1 = cluster.node_uris[0]
    uri_2 = cluster.node_uris[1]
    uri_3 = cluster.node_uris[2]

    ts_1 = cluster.nodes[uri_1]
    ts_2 = cluster.nodes[uri_2]
    ts_3 = cluster.nodes[uri_3]

    cluster.test_trace.start_subtest("Initial election, normal, then a couple of message processing error are inserted",
                                     test_path_str=str('/'.join(Path(__file__).parts[-2:])),
                                     test_doc_string=test_message_errors.__doc__)

    error_counter = 0
    class ErrorHandler(EventHandler):

        def __init__(self):
            super().__init__(event_types=[EventType.error,])

        async def on_event(self, event):
            nonlocal error_counter
            error_counter += 1
            
    for ts in [ts_1, ts_2, ts_3]:
        await ts.hull.add_event_handler(ErrorHandler())
    
    await cluster.start()
    await ts_3.start_campaign()
    sequence = SNormalElection(cluster, 1)
    await cluster.run_sequence(sequence)
    assert ts_3.get_role_name() == "LEADER"
    assert ts_1.get_leader_uri() == uri_3
    assert ts_2.get_leader_uri() == uri_3
    
    ts_1.hull.explode_on_message_code = AppendEntriesMessage.get_code()
    
    hist = ts_1.get_message_problem_history(clear=True)
    await ts_3.send_heartbeats()
    await ts_3.do_next_out_msg()
    await ts_3.do_next_out_msg()
    await ts_1.do_next_in_msg()
    await asyncio.sleep(0)
    assert error_counter == 1
    hist = ts_1.get_message_problem_history(clear=True)
    assert len(hist) == 1
    
    ts_1.hull.explode_on_message_code = None

    ts_1.hull.corrupt_message_with_code = AppendEntriesMessage.get_code()
    await ts_3.send_heartbeats()
    await ts_3.do_next_out_msg()
    await ts_3.do_next_out_msg()
    await ts_1.do_next_in_msg()
    await asyncio.sleep(0)
    assert error_counter == 2
    hist = ts_1.get_message_problem_history(clear=True)
    assert len(hist) == 1
    
    
    
