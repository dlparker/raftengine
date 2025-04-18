#!/usr/bin/env python
import asyncio
import logging
import pytest
import time
from raftengine.hull.hull import Hull
from raftengine.messages.request_vote import RequestVoteMessage,RequestVoteResponseMessage
from raftengine.messages.append_entries import AppendEntriesMessage, AppendResponseMessage
from raftengine.api.types import RoleName, SubstateCode

from dev_tools.servers import PausingCluster, cluster_maker
from dev_tools.servers import setup_logging

setup_logging()
logger = logging.getLogger("test_code")

async def test_bogus_pilot(cluster_maker):
    """
    Ensures that Hull constructor rejects Pilot class that does
    not implement PilotAPI
    """
    cluster = cluster_maker(3)
    config = cluster.build_cluster_config()
    cluster.set_configs(config)
    uri_1 = cluster.node_uris[0]
    ts_1 = cluster.nodes[uri_1]
    class BadPilot:
        pass
    with pytest.raises(Exception):
        Hull(ts_1.cluster_config, ts_1.local_config, BadPilot())

async def test_str_methods():
    """
    Ensures that __str__ methods of internal classes don't blow
    up when called, and that the result contains at least something
    of the expected information. Not much of a test, but the
    doesn't-blow-up part is useful.
    """
    assert str(RoleName.leader) == 'LEADER'
    assert str(SubstateCode.starting) == 'STARTING'
    assert "request_vote" in str(RequestVoteMessage('a','b', 0, 0, 0))
    assert "request_vote_response" in str(RequestVoteResponseMessage('a','b', 0, 0, 0, True))
    assert "v=True" in str(RequestVoteResponseMessage('a','b', 0, 0, 0, True))
    assert "v=False" in str(RequestVoteResponseMessage('a','b', 0, 0, 0, False))
    assert "append_entries" in str(AppendEntriesMessage('a','b', 0, 0, 0, entries=[]))
    assert "append_response" in str(AppendResponseMessage('a','b', 0, 0, 0, 0, True, 'a'))
    assert "s=True" in str(AppendResponseMessage('a','b', 0, 0, 0, 0, True, 'a'))
    assert "s=False" in str(AppendResponseMessage('a','b', 0, 0, 0, 0, False, 'a'))
