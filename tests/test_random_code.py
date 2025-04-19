#!/usr/bin/env python
import asyncio
import logging
import pytest
import time
from pathlib import Path
from raftengine.hull.hull import EventType, EventHandler
from raftengine.messages.request_vote import RequestVoteMessage,RequestVoteResponseMessage
from raftengine.messages.append_entries import AppendEntriesMessage, AppendResponseMessage
from dev_tools.servers import SNormalElection, SNormalCommand, SPartialElection, SPartialCommand
from dev_tools.servers import setup_logging
from dev_tools.servers import WhenElectionDone
from dev_tools.servers import PausingCluster, cluster_maker

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

async def not_a_test_event_perf(cluster_maker):
    if False:
        print('')
        print('-' * 120)
        print('running three warmup passes')
        await event_perf_inner(cluster_maker)
        await event_perf_inner(cluster_maker)
        await event_perf_inner(cluster_maker)
    print('')
    print('-' * 120)
    print('runnin no events')
    r1 = await event_perf_inner(cluster_maker)
    print('')
    print('-' * 120)
    print('running major events')
    r2 = await event_perf_inner(cluster_maker, [EventType.role_change,])
    print('')
    print('-' * 120)
    print('running msg events')
    r3 = await event_perf_inner(cluster_maker, [EventType.msg_handled,])
    print('')
    print('-' * 120)
    print('running major and msg events')
    r20 = await event_perf_inner(cluster_maker, [EventType.role_change, EventType.msg_handled,])
    print('-' * 120)
    print("")
    t1 = r1['election_etime']
    t2 = r2['election_etime']
    t3 = r3['election_etime']
    t20 = r20['election_etime']
    print("election times")
    diff = 0.0
    print(f'no events                              = {t1:8.8f} cost = {diff:8.8f}')
    diff = t2-t1
    print(f'major                                  = {t2:8.8f} cost = {diff:8.8f}')
    diff = t3-t1
    print(f'msg_events                             = {t3:8.8f} cost = {diff:8.8f}')
    diff = t20-t1
    print(f'msg, major                             = {t20:8.8f} cost = {diff:8.8f}')
    print('-' * 120)
    t1 = r1['command_etime']
    t2 = r2['command_etime']
    t3 = r3['command_etime']
    t20 = r20['command_etime']
    print("command times")
    diff = 0.0
    print(f'no events                              = {t1:8.8f} cost = {diff:8.8f}')
    diff = t2-t1
    print(f'major                                  = {t2:8.8f} cost = {diff:8.8f}')
    diff = t3-t1
    print(f'msg_events                             = {t3:8.8f} cost = {diff:8.8f}')
    diff = t20-t1
    print(f'msg, major                             = {t20:8.8f} cost = {diff:8.8f}')

    
async def event_perf_inner(cluster_maker, events=None):

    cluster = cluster_maker(3)
    cluster.set_configs()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]
    logger = logging.getLogger("test_code")

    if events:
        if EventType.role_change in events:
            class RoleChangeHandler(EventHandler):
                def __init__(self):
                    super().__init__(event_types=[EventType.role_change,])
                    
                async def on_event(self, event):
                    print(f"{event.event_type} {event.new_role}")

            class TermChangeHandler(EventHandler):
                def __init__(self):
                    super().__init__(event_types=[EventType.term_change,])
                    
                async def on_event(self, event):
                    print(f"{event.event_type} term={event.new_term}")

            for ts in [ts_1, ts_2, ts_3]:
                ts.hull.event_control.add_handler(RoleChangeHandler())
                ts.hull.event_control.add_handler(TermChangeHandler())
            
        if EventType.msg_handled in events:
            class MsgHandler(EventHandler):

                def __init__(self):
                    super().__init__(event_types=[EventType.msg_handled,
                                                  EventType.msg_recv,
                                                  EventType.msg_sent,])
                    
                async def on_event(self, event):
                    print(f"{event.event_type} {event.msg_type}")
                    
            class IndexChangeHandler(EventHandler):
                def __init__(self):
                    super().__init__(event_types=[EventType.index_change,])
                    
                async def on_event(self, event):
                    print(f"{event.event_type} index={event.new_index}")
                    
            class CommitChangeHandler(EventHandler):
                def __init__(self):
                    super().__init__(event_types=[EventType.commit_change,])
                    
                async def on_event(self, event):
                    print(f"{event.event_type} index={event.new_commit}")

            for ts in [ts_1, ts_2, ts_3]:
                ts.hull.event_control.add_handler(MsgHandler())
                ts.hull.event_control.add_handler(IndexChangeHandler())
                ts.hull.event_control.add_handler(CommitChangeHandler())

    
    await cluster.start()
    await ts_1.start_campaign()
    
    stime = time.perf_counter()
    await cluster.run_election()
    election_etime = time.perf_counter() - stime
    
    assert ts_1.get_role_name() == "LEADER"
    assert ts_2.get_leader_uri() == uri_1
    assert ts_3.get_leader_uri() == uri_1
    logger.info('------------------------ Election done')
    logger.info('---------!!!!!!! starting comms')


    #cfg = ts_1.cluster_config
    #loop_limit = cfg.max_entries_per_message * 2 + 2
    loop_limit = 2
    stime = time.perf_counter()
    for i in range(loop_limit):
        command_result = await cluster.run_command("add 1", 1)
    command_etime = time.perf_counter() - stime
    total = ts_1.operations.total
    assert ts_2.operations.total == total
    await cluster.stop_auto_comms()
    logger.info('------------------------ All done')
    return dict(election_etime=election_etime,
                command_etime=command_etime)

        
async def test_event_handlers(cluster_maker):
    
    cluster = cluster_maker(3)
    cluster.set_configs()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]
    logger = logging.getLogger("test_code")

    role_change_counter = 0
    term_change_counter = 0

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

    for ts in [ts_1, ts_2, ts_3]:
        ts.hull.event_control.add_handler(RoleChangeHandler())
        ts.hull.event_control.add_handler(TermChangeHandler())
        leader_handler = LeaderChangeHandler()
        ts.hull.event_control.add_handler(leader_handler)
            
    await cluster.start()
    await ts_1.start_campaign()
    
    await cluster.run_election()
    # each node should change to follower at start, thats 3
    # then ts_1 should change to candidate, then leader, thats 5
    assert role_change_counter == 5 # once to candidate, once to leader
    assert term_change_counter == 3 # once for each node


    sends = 0
    recvs = 0
    handles = 0
    index_changes = 0
    commit_changes = 0
    leader_uri = None
    class MsgHandler(EventHandler):
        def __init__(self):
            super().__init__(event_types=[EventType.msg_handled,
                                          EventType.msg_recv,
                                          EventType.msg_sent,])
            
        async def on_event(self, event):
            nonlocal sends
            nonlocal recvs
            nonlocal handles
            if event.event_type == EventType.msg_handled:
                if handles == 0:
                    print(f"first message of type {event.event_type}")
                handles += 1
            if event.event_type == EventType.msg_sent:
                if sends == 0:
                    print(f"first message of type {event.event_type}")
                sends += 1
            if event.event_type == EventType.msg_recv:
                if recvs == 0:
                    print(f"first message of type {event.event_type}")
                recvs += 1
            # make sure to_json does not blow up
            event.to_json()
                    
    class IndexChangeHandler(EventHandler):
        def __init__(self):
            super().__init__(event_types=[EventType.index_change,])
            
        async def on_event(self, event):
            nonlocal index_changes
            index_changes += 1
            # make sure to_json does not blow up
            event.to_json()
                    
    class CommitChangeHandler(EventHandler):
        def __init__(self):
            super().__init__(event_types=[EventType.commit_change,])
            
        async def on_event(self, event):
            nonlocal commit_changes
            commit_changes += 1
            # make sure to_json does not blow up
            event.to_json()


    msg_handler = MsgHandler()
    index_handler = IndexChangeHandler()
    commit_handler = CommitChangeHandler()
    for ts in [ts_1, ts_2, ts_3]:
        ts.hull.event_control.add_handler(msg_handler)
        ts.hull.event_control.add_handler(index_handler)
        ts.hull.event_control.add_handler(commit_handler)
    
    command_result = await cluster.run_command("add 1", 1)
    await cluster.deliver_all_pending()
    assert sends > 0
    assert sends == recvs == handles
    assert index_changes == 1
    assert commit_changes == 1
    
    sends = 0
    recvs = 0
    handles = 0
    for ts in [ts_1, ts_2, ts_3]:
        ts.hull.event_control.remove_handler(msg_handler)
        
    command_result = await cluster.run_command("add 1", 1)
    await cluster.deliver_all_pending()
    assert sends == recvs == handles == 0
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
        ts.hull.event_control.add_handler(ErrorHandler())
    
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
    
    assert error_counter == 1
    hist = ts_1.get_message_problem_history(clear=True)
    assert len(hist) == 1
    
    ts_1.hull.explode_on_message_code = None

    ts_1.hull.corrupt_message_with_code = AppendEntriesMessage.get_code()
    await ts_3.send_heartbeats()
    await ts_3.do_next_out_msg()
    await ts_3.do_next_out_msg()
    await ts_1.do_next_in_msg()
    assert error_counter == 2
    hist = ts_1.get_message_problem_history(clear=True)
    assert len(hist) == 1
    
    
    
