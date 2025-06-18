#!/usr/bin/env python
import asyncio
import pytest
import logging

from dev_tools.pausing_cluster import cluster_maker
from dev_tools.logging_ops import setup_logging



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

    
async def test_get_hull():
    from raftengine.api import get_hull_class
    from raftengine.api.hull_config import ClusterInitConfig, LocalConfig
    from dev_tools.memory_log import MemoryLog
    from raftengine.api.pilot_api import PilotAPI

    class PilotSim(PilotAPI):

        def __init__(self):
            self.log = MemoryLog()
                        
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
        
        async def begin_snapshot_import(self, index, term):
            raise NotImplementedError
        
        async def begin_snapshot_export(self, snapshot):
            raise NotImplementedError

    cls = get_hull_class()
    cc = ClusterInitConfig(node_uris=['foo1', 'foo2', 'foo3'],
                           heartbeat_period=1,
                           election_timeout_min=1,
                           election_timeout_max=1,
                           max_entries_per_message=10)
    local_config = LocalConfig(uri="foo1",
                               working_dir='/tmp/',
                               )
    hull = cls(cc, local_config, PilotSim())

async def test_tracing_demo(cluster_maker, trace_style='new'):
    """
    Test the simplest snapshot process, at a follower in a quiet cluster. After
    it is installed, have that node become the leader and make sure new commands
    work.

    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    
    """
    cluster = cluster_maker(3)
    config = cluster.build_cluster_config(use_pre_vote=False)
    cluster.set_configs(config)

    if trace_style == "new":
        uses = ['election', 'command']
        cluster.test_trace.define_test("Starting election at node 1 of 3", uses, [])
    else:
        cluster.test_trace.start_subtest("Starting election at node 3",
                                         test_path_str=str('/'.join(Path(__file__).parts[-2:])),
                                         test_doc_string=test_stepwise_election_1.__doc__)
    
    await cluster.start()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]
    
    await ts_1.start_campaign()
    await cluster.run_election()
    cluster.test_trace.start_subtest("Node 1 is leader")

    

    
