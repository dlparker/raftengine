#!/usr/bin/env python
import logging
from pathlib import Path
import time
import asyncio
import pytest

from dev_tools.memory_log import MemoryLog
from dev_tools.servers import cluster_maker
from dev_tools.servers import setup_logging
from raftengine.api.pilot_api import PilotAPI
from raftengine.api.log_api import LogRec
from raftengine.api.types import NodeRec, ClusterConfig
from raftengine.hull.hull import Hull
from raftengine.messages.cluster_change import MembershipChangeMessage, ChangeOp, MembershipChangeResponseMessage

#extra_logging = [dict(name=__name__, level="debug"),]
#setup_logging(extra_logging)
default_level="error"
#default_level="debug"
setup_logging(default_level=default_level)
logger = logging.getLogger("test_code")

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

    async def stop_commanded(self) -> None:
        raise NotImplementedError

async def test_member_change_messages(cluster_maker):

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

    
async def atest_log_config_ops(cluster_maker):
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
    log.start()
    
    hull = Hull(cluster_config=tconfig, local_config=local_config, pilot = PilotSim(log))
    c_ops = hull.cluster_ops
    cc = await hull.get_cluster_config()
    
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


async def test_remove_follower_1(cluster_maker):
    """
    Simple case of removing a follower from the cluster. 
    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """
    
    cluster = cluster_maker(3)
    config = cluster.build_cluster_config(use_pre_vote=False)
    cluster.set_configs(config)

    cluster.test_trace.start_subtest("Starting election at node 1 of 5",
                                     test_path_str=str('/'.join(Path(__file__).parts[-2:])),
                                     test_doc_string=test_remove_follower_1.__doc__)
    await cluster.start()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]

    await ts_1.start_campaign()
    # vote requests, then vote responses
    await cluster.deliver_all_pending()
    assert ts_1.get_role_name() == "LEADER"
    cluster.test_trace.start_subtest("Node 1 is leader, sending heartbeat so replies will tell us that followers did commit")
    # append entries, then responses
    await cluster.deliver_all_pending()
    assert ts_2.get_leader_uri() == uri_1
    assert ts_3.get_leader_uri() == uri_1
    await ts_1.send_heartbeats()
    await cluster.deliver_all_pending()

    print("\n\n\nRemoving node 3\n\n\n")
    # now remove number 3
    await ts_3.exit_cluster()
    await cluster.deliver_all_pending()
    await ts_1.send_heartbeats()
    await cluster.deliver_all_pending()
    assert ts_3.hull.role.stopped

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

    cluster.test_trace.start_subtest("Starting election at node 1 of 5",
                                     test_path_str=str('/'.join(Path(__file__).parts[-2:])),
                                     test_doc_string=test_remove_leader_1.__doc__)
    await cluster.start()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]

    await ts_1.start_campaign()
    # vote requests, then vote responses
    await cluster.deliver_all_pending()
    assert ts_1.get_role_name() == "LEADER"
    cluster.test_trace.start_subtest("Node 1 is leader, sending heartbeat so replies will tell us that followers did commit")
    # append entries, then responses
    await cluster.deliver_all_pending()
    assert ts_2.get_leader_uri() == uri_1
    assert ts_3.get_leader_uri() == uri_1
    await ts_1.send_heartbeats()
    await cluster.deliver_all_pending()

    print("\n\n\nRemoving leader node 1\n\n\n")
    await ts_1.exit_cluster()
    await cluster.deliver_all_pending()
    await ts_1.send_heartbeats()
    start_time = time.time()
    while time.time() - start_time < 1.0:
        if ts_2.get_role_name() == "LEADER" or ts_3.get_role_name() == "LEADER":
            break
        if ts_1.hull is None:
            break
        await asyncio.sleep(0.01)
        await cluster.deliver_all_pending()
        
    assert ts_2.get_role_name() == "LEADER" or ts_3.get_role_name() == "LEADER"
    await asyncio.sleep(0.01)
    assert ts_1.hull.role.stopped

async def test_add_follower_1(cluster_maker):
    """
    Simple case of adding a follower to the cluster with a short log, only a term start and one command." 
    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """
    
    cluster = cluster_maker(3)
    config = cluster.build_cluster_config(use_pre_vote=False)
    cluster.set_configs(config)

    cluster.test_trace.start_subtest("Starting election at node 1 of 5",
                                     test_path_str=str('/'.join(Path(__file__).parts[-2:])),
                                     test_doc_string=test_remove_leader_1.__doc__)
    await cluster.start()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]

    await ts_1.start_campaign()
    # vote requests, then vote responses
    await cluster.deliver_all_pending()
    assert ts_1.get_role_name() == "LEADER"
    cluster.test_trace.start_subtest("Node 1 is leader, sending heartbeat so replies will tell us that followers did commit")
    # append entries, then responses
    await cluster.deliver_all_pending()
    assert ts_2.get_leader_uri() == uri_1
    assert ts_3.get_leader_uri() == uri_1
    await ts_1.send_heartbeats()
    await cluster.deliver_all_pending()
    
    command_result = await cluster.run_command("add 1", 1)
    assert ts_1.operations.total == 1
    ts_4 = await cluster.add_node()
    leader = cluster.get_leader()
    await ts_4.start_and_join(leader.uri)
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
    Adding a follower to the cluster with a long log, filled with a couple hundred entries. We are
    cheating by directly adding the entries to each member node before the add, just to keep the
    logging, time and tracing down.
    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """
    
    cluster = cluster_maker(3)
    config = cluster.build_cluster_config(use_pre_vote=False)
    cluster.set_configs(config)

    cluster.test_trace.start_subtest("Starting election at node 1 of 5",
                                     test_path_str=str('/'.join(Path(__file__).parts[-2:])),
                                     test_doc_string=test_remove_leader_1.__doc__)
    await cluster.start()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]

    await ts_1.start_campaign()
    # vote requests, then vote responses
    await cluster.deliver_all_pending()
    assert ts_1.get_role_name() == "LEADER"
    cluster.test_trace.start_subtest("Node 1 is leader, sending heartbeat so replies will tell us that followers did commit")
    # append entries, then responses
    await cluster.deliver_all_pending()
    assert ts_2.get_leader_uri() == uri_1
    assert ts_3.get_leader_uri() == uri_1
    await ts_1.send_heartbeats()
    await cluster.deliver_all_pending()
    for i in range(2, 202):
        rec = LogRec(index=i, term=1, command="add 1", leader_id=ts_1.uri, committed=True, applied=True)
        for ts in [ts_1, ts_2, ts_3]:
            await ts.log.append(rec)
            ts.operations.total += 1
    for ts in [ts_1, ts_2, ts_3]:
        assert await ts.log.get_last_term() == 1
        assert await ts.log.get_last_index() == 201
        assert await ts.log.get_commit_index() == 201
        assert await ts.log.get_applied_index() == 201
        ts.operations.total == 200
    ts_4 = await cluster.add_node()
    leader = cluster.get_leader()
    await ts_4.start_and_join(leader.uri)
    start_time = time.time()
    while time.time() - start_time < 0.1:
        cc = await ts_1.log.get_cluster_config()
        if ts_4.uri in cc.nodes:
            break
        await cluster.deliver_all_pending()
        await asyncio.sleep(0.001)

    assert ts_4.operations.total == ts_1.operations.total

    
