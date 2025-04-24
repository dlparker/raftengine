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
