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
    from dev_tools.memory_log import MemoryLog
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


