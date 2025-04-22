#!/usr/bin/env python
import asyncio
import logging
import time
import json
from pathlib import Path
from pprint import pprint
import pytest
from raftengine.hull.hull import EventType, EventHandler
from raftengine.api.log_api import LogRec, RecordCode
from raftengine.api.hull_config import ClusterConfig
from dev_tools.memory_log import MemoryLog
from dev_tools.servers import SNormalElection, SNormalCommand, SPartialElection, SPartialCommand
from dev_tools.servers import setup_logging
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

async def save_cluster_op(log, op, config, operand=None):
    command = dict(op=op, config=config, operand=operand)
    encoded = json.dumps(command, default=lambda o:o.__dict__)
    rec = LogRec(code=RecordCode.cluster_config, command=encoded)
    rec_back = await log.append(rec)
    return rec_back

async def get_cluster_op(log, rec_id):
    rec = await log.read(rec_id)
    command = json.loads(rec.command)
    op = command['op']
    jconfig = command['config']
    config = ClusterConfig.from_dict(jconfig)
    operand = command['operand']
    return op, config, operand

async def test_log_config(cluster_maker):
    log = MemoryLog()
    log.start()
    cluster = cluster_maker(3)
    config = cluster.build_cluster_config(election_timeout_min=0.01,
                                          election_timeout_max=0.011)
    rec_ids = []
    rec_1 = await save_cluster_op(log, "save", config)
    rec_ids.append(rec_1.index)
    new_node = cluster.add_node()
    rec_2 = await save_cluster_op(log, "add_node", config, new_node.uri)
    rec_ids.append(rec_2.index)
    config.node_uris.append(new_node.uri)
    rec_3 = await save_cluster_op(log, "apply", config)
    rec_ids.append(rec_3.index)
    rec_4 = await save_cluster_op(log, "remove_node", config, new_node.uri)
    rec_ids.append(rec_4.index)
    config.node_uris.remove(new_node.uri)
    await cluster.remove_node(new_node.uri)
    rec_5 = await save_cluster_op(log, "apply", config)
    rec_ids.append(rec_5.index)
    
    print('')
    for rec_id in rec_ids:
        op, config, operand = await get_cluster_op(log, rec_id)
        pprint(f"op='{op}', operand='{operand}', config={config}")

    

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

