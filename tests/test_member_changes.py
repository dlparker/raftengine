#!/usr/bin/env python
import logging
from pathlib import Path
import pytest

from dev_tools.memory_log import MemoryLog
from dev_tools.servers import cluster_maker
from dev_tools.servers import setup_logging
from raftengine.api.pilot_api import PilotAPI
from raftengine.api.types import NodeRec, ClusterConfig
from raftengine.hull.hull import Hull

#extra_logging = [dict(name=__name__, level="debug"),]
#setup_logging(extra_logging)
default_level="error"
default_level="debug"
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


async def test_log_config_ops(cluster_maker):
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
    cc = await hull.get_cluster_config()
    
    uri = 'mcpy://4'
    await hull.start_node_add(uri)
    with pytest.raises(Exception):
        await hull.finish_node_add(uri)
    with pytest.raises(Exception):
        await hull.start_node_add('mcpy://5')
    with pytest.raises(Exception):
        await hull.start_node_remove(uri)
    assert await hull.node_is_voter(uri) is False
    await hull.node_add_prepared(uri)
    assert await hull.node_is_voter(uri) is True
    cc4 = await hull.finish_node_add(uri)
    assert uri in cc4.nodes
    with pytest.raises(Exception):
        await hull.start_node_add(uri)
    with pytest.raises(Exception):
        await hull.node_add_prepared(uri)
    with pytest.raises(Exception):
        await hull.finish_node_add(uri)
    await hull.start_node_remove(uri)
    assert uri not in cc4.nodes
    assert await hull.node_is_voter(uri) is True
    with pytest.raises(Exception):
        await hull.start_node_add('mcpy://5')
    with pytest.raises(Exception):
        await hull.start_node_remove('mcpy://5')
    cc5 = await hull.finish_node_remove(uri)
    assert uri not in cc5.nodes
    assert cc5.pending_node is None
    with pytest.raises(Exception):
        await hull.start_node_remove(uri)
    with pytest.raises(Exception):
        await hull.finish_node_remove(uri)


async def test_node_remove_1(cluster_maker):
    """
    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """
    
    cluster = cluster_maker(5)
    config = cluster.build_cluster_config(use_pre_vote=False)
    cluster.set_configs(config)

    cluster.test_trace.start_subtest("Starting election at node 1 of 5",
                                     test_path_str=str('/'.join(Path(__file__).parts[-2:])),
                                     test_doc_string=test_node_remove_1.__doc__)
    await cluster.start()
    uri_1, uri_2, uri_3, uri_4, uri_5 = cluster.node_uris
    ts_1, ts_2, ts_3, ts_4, ts_5 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3, uri_4, uri_5]]

    await ts_1.start_campaign()
    # vote requests, then vote responses
    await cluster.deliver_all_pending()
    assert ts_1.get_role_name() == "LEADER"
    cluster.test_trace.start_subtest("Node 1 is leader, sending heartbeat so replies will tell us that followers did commit")
    # append entries, then responses
    await cluster.deliver_all_pending()
    assert ts_2.get_leader_uri() == uri_1
    assert ts_3.get_leader_uri() == uri_1
    assert ts_4.get_leader_uri() == uri_1
    assert ts_5.get_leader_uri() == uri_1
    await ts_1.send_heartbeats()
    await cluster.deliver_all_pending()

    # now remove number 5
    await ts_5.exit_cluster()
    await cluster.deliver_all_pending()
    await cluster.deliver_all_pending()
