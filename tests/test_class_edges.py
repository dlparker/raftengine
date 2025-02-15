#!/usr/bin/env python
import asyncio
import logging
import pytest
import time
from raftengine.hull.hull import Hull
from raftengine.messages.request_vote import RequestVoteMessage,RequestVoteResponseMessage
from raftengine.messages.append_entries import AppendEntriesMessage, AppendResponseMessage

from tests.servers import PausingCluster, cluster_maker
from tests.servers import setup_logging

extra_logging = [dict(name=__name__, level="debug"),]
setup_logging(extra_logging)

async def test_bogus_pilot(cluster_maker):
    cluster = cluster_maker(3)
    config = cluster.build_cluster_config()
    cluster.set_configs(config)
    uri_1 = cluster.node_uris[0]
    ts_1 = cluster.nodes[uri_1]
    class BadPilot:
        pass
    with pytest.raises(Exception):
        Hull(ts_1.cluster_config, ts_1.local_config, BadPilot())
