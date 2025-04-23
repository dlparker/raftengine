#!/usr/bin/env python
import asyncio
import logging
import time
import json
from pathlib import Path
from pprint import pprint
import pytest
from raftengine.hull.hull import EventType, EventHandler, Hull
from raftengine.api.types import ClusterConfig, NodeRec, ClusterSettings
from raftengine.api.log_api import LogRec, RecordCode, LogAPI
from raftengine.api.pilot_api import PilotAPI
from raftengine.api.hull_config import ClusterInitConfig
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

class PilotSim(PilotAPI):

    def __init__(self, log):
        self.log = log

    def get_log(self):
        return self.log
    
    async def process_command(self, command: str, serial: int):
        raise NotImplementedError

    async def send_message(self, target_uri: str, message:str):
        raise NotImplementedError

    async def send_response(self, target_uri: str, orig_message:str, reply:str):
        raise NotImplementedError


class HullSim(Hull):

    async def setup_cluster_config(self):
        log = self.get_log()
        stored_config = await log.get_cluster_config()
        if stored_config:
            return stored_config
        
        for uri in self.cluster_init_config.node_uris:
            nd[uri] = NodeRec(uri)
        cc = ClusterConfig(nodes=nd)
        await log.save_cluster_config(cc)
        self.cluster_config
        return await log.get_cluster_config()

    async def get_cluster_config(self):
        config = await self.log.get_cluster_config()
        if not config:
            return await self.setup_cluster_config()
        return config
        
    async def start_node_add(self, node_uri):
        cc = await self.get_cluster_config()
        if cc.pending_node:
            raise Exception(f"cluster memebership change already in progress with node {cc.pending_node.uri}")
        if node_uri not in cc.nodes:
            rec = NodeRec(node_uri)
            cc.pending_node = rec
            rec.is_adding = True
            rec.is_loading = True
            return await self.log.save_cluster_config(cc)
        raise Exception(f'node {node_uri} is already in active node set')

    async def node_add_prepared(self, node_uri):
        cc = await self.get_cluster_config()
        if cc.pending_node is None or cc.pending_node.uri != node_uri:
            raise Exception(f'node {node_uri} is not pending add')
        cc.pending_node.is_loading = False
        return await self.log.save_cluster_config(cc)
        
    async def apply_node_add(self, node_uri):
        cc = await self.get_cluster_config()
        if cc.pending_node is not None and cc.pending_node.uri == node_uri and cc.pending_node.is_adding:
            if cc.pending_node.is_loading:
                raise Exception(f"Cannot apply add on node {node_uri}, it hasn't been loaded yet")
            cc.pending_node.is_adding = False
            cc.nodes[node_uri] = cc.pending_node
            cc.pending_node = None
            return await self.log.save_cluster_config(cc)
        raise Exception(f'node {node_uri} is not pending addition')

    async def start_node_remove(self, node_uri):
        cc = await self.get_cluster_config()
        if cc.pending_node:
            raise Exception(f"cannot remove node {node_uri}, another action is pending for node {cc.pending_node.uri}")
        if node_uri in cc.nodes:
            rec = cc.nodes[node_uri]
            cc.pending_node = rec
            rec.is_removing = True
            del cc.nodes[node_uri]
            return await self.log.save_cluster_config(cc)
        raise Exception(f'node {node_uri} is not in active node set')

    async def apply_node_remove(self, node_uri):
        cc = await self.get_cluster_config()
        if cc.pending_node is not None and cc.pending_node.uri == node_uri and cc.pending_node.is_removing:
            cc.pending_node = None
            return await self.log.save_cluster_config(cc)
        raise Exception(f'node {node_uri} is not pending removal')

    async def node_is_voter(self, node_uri):
        cc = await self.get_cluster_config()
        # leader gets the wrong answer here if itself is removing, so leader needs a different check
        if (cc.pending_node 
            and cc.pending_node.uri == node_uri
            and cc.pending_node.is_loading):
            return False
        return True
            
        
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
    config = ClusterInitConfig.from_dict(jconfig)
    operand = command['operand']
    return op, config, operand

async def txest_save_config(cluster_maker):
    cluster = cluster_maker(3)
    config = cluster.build_cluster_config(election_timeout_min=0.01,
                                          election_timeout_max=0.011)
    cluster.set_configs()
    
    nd = {}
    for uri in config.node_uris:
        nd[uri] = NodeRec(uri)
        local_config = cluster.nodes[uri].local_config
        
    cc = ClusterConfig(nodes=nd)
    log = MemoryLog()
    log.start()

    await log.save_cluster_config(cc)
    cc2 = await log.get_cluster_config()
    assert cc is not cc2
    assert cc == cc2

    
    hull = HullSim(cluster_config=config, local_config=local_config, pilot = PilotSim(log))
    cc3 = await hull.get_cluster_config()
    
    assert cc == cc3
    uri = 'mcpy://4'
    await hull.start_node_add(uri)
    with pytest.raises(Exception):
        await hull.apply_node_add(uri)
    with pytest.raises(Exception):
        await hull.start_node_add('mcpy://5')
    with pytest.raises(Exception):
        await hull.start_node_remove(uri)
    assert await hull.node_is_voter(uri) is False
    await hull.node_add_prepared(uri)
    assert await hull.node_is_voter(uri) is True
    cc4 = await hull.apply_node_add(uri)
    assert uri in cc4.nodes
    cc5 = await hull.start_node_remove(uri)
    assert uri not in cc4.nodes
    assert await hull.node_is_voter(uri) is True
    with pytest.raises(Exception):
        await hull.start_node_add('mcpy://5')
    with pytest.raises(Exception):
        await hull.start_node_remove('mcpy://5')
    
        
async def xtest_log_config(cluster_maker):
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

