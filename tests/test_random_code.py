#!/usr/bin/env python
import asyncio
import pytest
import logging
from typing import Any

# Temp, remove when feature code is done
from dataclasses import dataclass, field
from typing import Optional
from dev_tools.triggers import WhenMessageOut, WhenMessageIn
from raftengine.messages.append_entries import AppendResponseMessage
from dev_tools.sequences import SPartialCommand
from raftengine.api.snapshot_api import SnapShot
from raftengine.api.log_api import LogRec
from raftengine.api.types import NodeRec, ClusterSettings, ClusterConfig
import time
import json 

from dev_tools.pausing_cluster import cluster_maker
from dev_tools.log_control import setup_logging
from dev_tools.features import FeatureRegistry
registry = FeatureRegistry.get_registry()


#setup_logging(extra_logging)
default_level='error'
#default_level='debug'
log_control = setup_logging()
# Set custom levels for specific loggers
log_control.set_logger_level("test_code", "debug")
log_control.set_logger_level("Leader", "debug")
log_control.set_logger_level("Candidate", "debug")
log_control.set_logger_level("Follower", "debug")
logger = logging.getLogger("test_code")


# Stuff in here is just things that help me develop tests by writing
# explority code that runs in the test context, just to figure out
# what will work before adding it to real code.
# I might keep old code around for a while by renaming the test so
# it won't be gathered, then remove it when I am sure there is no
# more need for it.

async def test_get_deck():
    from raftengine.api import get_deck_class
    from raftengine.api.deck_config import ClusterInitConfig, LocalConfig
    from raftengine_logs.memory_log import MemoryLog
    from raftengine.api.pilot_api import PilotAPI

    class PilotSim(PilotAPI):

        def __init__(self):
            self.log = MemoryLog()
                        
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

        
    cls = get_deck_class()
    cc = ClusterInitConfig(node_uris=['foo1', 'foo2', 'foo3'],
                           heartbeat_period=1,
                           election_timeout_min=1,
                           election_timeout_max=1,
                           max_entries_per_message=10)
    local_config = LocalConfig(uri="foo1",
                               working_dir='/tmp/',
                               )
    deck = cls(cc, local_config, PilotSim())


async def atest_command_1b(cluster_maker):
    from raftengine.lsfs.lsfs_raft_log import LSFSRaftLog
    cluster = cluster_maker(3, use_log=LSFSRaftLog)
    cluster.set_configs()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]
    logger = logging.getLogger("test_code")
    await cluster.test_trace.define_test("Testing command operations with SQLite log", logger=logger)
    f_normal_election = registry.get_raft_feature("leader_election", "all_yes_votes.with_pre_vote")
    spec = dict(used=[f_normal_election], tested=[])
    await cluster.test_trace.start_test_prep("Normal election", features=spec)
    await cluster.start()
    await ts_3.start_campaign()

    await cluster.run_election()
    assert ts_3.get_role_name() == "LEADER"
    assert ts_1.get_leader_uri() == uri_3
    assert ts_2.get_leader_uri() == uri_3
    logger.info('------------------------ Election done')
    await cluster.start_auto_comms()

    f_sqlite_compat = registry.get_raft_feature("log_storage", "sqlite_compatibility")
    f_state_machine_cmd = registry.get_raft_feature("state_machine_command", "all_in_sync")
    f_log_replication = registry.get_raft_feature("log_replication", "normal_replication")
    f_heartbeat = registry.get_raft_feature("log_replication", "heartbeat_only")
    spec = dict(used=[f_log_replication, f_heartbeat], tested=[f_sqlite_compat, f_state_machine_cmd])
    await cluster.test_trace.start_subtest("Run command and check results at all nodes", features=spec)
    command_result = await cluster.run_command("add 1", 1)
    
    assert ts_1.operations.total == 1
    assert ts_2.operations.total == 1
    assert ts_3.operations.total == 1
    term = await ts_3.log.get_term()
    index = await ts_3.log.get_last_index()
    assert index == 2 # first index will be the start term record
    assert await ts_1.log.get_term() == term
    assert await ts_1.log.get_last_index() == index
    assert await ts_2.log.get_term() == term
    assert await ts_2.log.get_last_index() == index
    logger.debug('------------------------ Correct command done')
    rec_1 = await ts_1.log.read(index)
    rec_2 = await ts_2.log.read(index)
    rec_3 = await ts_3.log.read(index)
    await cluster.stop_auto_comms()
