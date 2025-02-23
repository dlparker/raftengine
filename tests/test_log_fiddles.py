#!/usr/bin/env python
import asyncio
import logging
import pytest
import time
import traceback
from raftengine.messages.request_vote import RequestVoteMessage,RequestVoteResponseMessage
from raftengine.messages.append_entries import AppendEntriesMessage, AppendResponseMessage
from raftengine.api.log_api import LogRec
from dev_tools.memory_log import MemoryLog

from dev_tools.servers import WhenMessageOut, WhenMessageIn
from dev_tools.servers import WhenHasLogIndex
from dev_tools.servers import WhenHasCommitIndex
from dev_tools.servers import WhenInMessageCount, WhenElectionDone
from dev_tools.servers import WhenAllMessagesForwarded, WhenAllInMessagesHandled
from dev_tools.servers import PausingCluster, cluster_maker
from dev_tools.servers import SNormalElection, SNormalCommand, SPartialElection
from dev_tools.servers import setup_logging

extra_logging = [dict(name=__name__, level="debug"), dict(name="Triggers", level="debug")]
#extra_logging = [dict(name=__name__, level="debug"),]
log_config = setup_logging(extra_logging)

async def test_empty_log(cluster_maker):
    cluster = cluster_maker(3)
    # do real timer values, but start disabled
    heartbeat_period=0.005
    election_timeout_min=0.09
    election_timeout_max=0.11
    config = cluster.build_cluster_config(heartbeat_period=heartbeat_period,
                                          election_timeout_min=election_timeout_min,
                                          election_timeout_max=election_timeout_max)
    cluster.set_configs(config)

    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]
    logger = logging.getLogger(__name__)
    await cluster.start()
    await ts_1.hull.start_campaign()
    sequence = SNormalElection(cluster, 1)
    await cluster.run_sequence(sequence)
    
    assert ts_1.hull.get_state_code() == "LEADER"
    assert ts_2.hull.state.leader_uri == uri_1
    assert ts_3.hull.state.leader_uri == uri_1
    logger = logging.getLogger(__name__)
    logger.info('------------------------ Election done')

    for i in range(50):
        sequence2 = SNormalCommand(cluster, "add 1", 1)
        command_result = await cluster.run_sequence(sequence2)

    await cluster.deliver_all_pending()
    await cluster.start_auto_comms()
    assert ts_1.operations.total == 50
    # Now "crash" the leader, run an election, then have
    # the leader come up with an empty log
    await ts_1.hull.demote_and_handle(None)
    await ts_1.hull.state.stop()
    ts_1.operations.total = 0
    ts_1.block_network()

    await ts_2.enable_timers()
    await ts_3.enable_timers()
    logger.info('------------------------ Running Partial Election')
    sequence = SPartialElection(cluster, voters=[uri_2, uri_3])
    await cluster.run_sequence(sequence)

    # old leader is now ignorant of all past
    ts_1.hull.log = MemoryLog()
    ts_1.hull.state.log = MemoryLog()
    await ts_1.hull.state.start()

    # let the timers run so it things catch up normally
    logger.info('------------------------ Restoring timers and waiting for ts_1 to catch up')
    ts_1.unblock_network()
    await ts_1.enable_timers()
    start_time = time.time()
    while (time.time() - start_time < election_timeout_max * 2
           and ts_1.operations.total != 50):
        await asyncio.sleep(0.0001)
    assert ts_1.operations.total == 50        
    await cluster.stop_auto_comms()
    logger.debug('------------------------ Tardy follower caught up ---')

