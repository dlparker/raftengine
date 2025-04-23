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


async def test_save_config(cluster_maker):
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
    
    hull = Hull(cluster_config=config, local_config=local_config, pilot = PilotSim(log))
    cc3 = await hull.get_cluster_config()
    
    assert cc is not  cc3
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
    with pytest.raises(Exception):
        await hull.start_node_add(uri)
    with pytest.raises(Exception):
        await hull.node_add_prepared(uri)
    with pytest.raises(Exception):
        await hull.apply_node_add(uri)
    cc5 = await hull.start_node_remove(uri)
    assert uri not in cc4.nodes
    assert await hull.node_is_voter(uri) is True
    with pytest.raises(Exception):
        await hull.start_node_add('mcpy://5')
    with pytest.raises(Exception):
        await hull.start_node_remove('mcpy://5')
    cc5 = await hull.apply_node_remove(uri)
    assert uri not in cc5.nodes
    assert cc5.pending_node is None
    with pytest.raises(Exception):
        await hull.start_node_remove(uri)
    with pytest.raises(Exception):
        await hull.apply_node_remove(uri)
    
