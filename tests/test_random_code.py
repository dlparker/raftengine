#!/usr/bin/env python
import asyncio
import pytest
import logging

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
