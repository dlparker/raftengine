#!/usr/bin/env python
import asyncio
import logging
import time
from pathlib import Path
import pytest
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

#extra_logging = [dict(name=__name__, level="debug"), dict(name="Triggers", level="debug")]
#extra_logging = [dict(name=__name__, level="debug"),]
#log_config = setup_logging(extra_logging)
default_level='error'
#default_level='debug'
setup_logging(default_level=default_level)
logger = logging.getLogger("test_code")

async def test_empty_log_1(cluster_maker):
    """
    Tests that a leader crash and recovery with an empty log eventually leads to a successful
    sync with the rest of the cluster.

    Test starts with normal election, then the leader is crashed, and election is run,
    and then the leader is restarted but with an empty log. The timer driven operations
    are then allowe to proceed until the leader is caught up and in sync.
    
    Timers are disabled during the first election, so during that phase
    all timer driven operations such as heartbeats are manually triggered.
    After the leader is crashed, timers are enabled and remain enabled for the rest
    of the test.
    
    """
    cluster = cluster_maker(3)
    # do real timer values, but start in the usual disabled state.
    heartbeat_period=0.005
    election_timeout_min=0.09
    election_timeout_max=0.11
    config = cluster.build_cluster_config(heartbeat_period=heartbeat_period,
                                          election_timeout_min=election_timeout_min,
                                          election_timeout_max=election_timeout_max)
    cluster.set_configs(config)

    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]
    cluster.test_trace.start_subtest("Initial election, normal but not using timers",
                                     test_path_str=str('/'.join(Path(__file__).parts[-2:])),
                                     test_doc_string=test_empty_log_1.__doc__)
    await cluster.start()
    await ts_1.start_campaign()
    await cluster.run_election()
    
    assert ts_1.get_role_name() == "LEADER"
    assert ts_2.get_leader_uri() == uri_1
    assert ts_3.get_leader_uri() == uri_1
    logger.info('------------------------ Election done')

    cfg = ts_1.cluster_init_config
    # enough to get two full and one partial append_entries catchups.
    loop_limit = cfg.max_entries_per_message * 2 + 2
    await cluster.start_auto_comms()
    cluster.test_trace.start_subtest(f"Node 1 is leader, running {loop_limit} commands to fill log")
    for i in range(loop_limit):
        command_result = await cluster.run_command("add 1", 1)
    await cluster.stop_auto_comms()

    assert ts_1.operations.total == loop_limit
    # Now "crash" the leader, run an election, then have
    # the leader come up with an empty log
    cluster.test_trace.start_subtest("Crashing leader node 1, clearing its log, restarting it, then letting timers run until catchup done")
    await ts_1.simulate_crash()

    await cluster.start_auto_comms()
    await ts_2.enable_timers()
    await ts_3.enable_timers()
    logger.info('------------------------ Running Partial Election')
    await cluster.run_election()

    # let the timers run so it things catch up normally
    logger.info('------------------------ Restoring timers and waiting for ts_1 to catch up')
    # old leader is now ignorant of all past
    await ts_1.recover_from_crash(save_log=False, save_ops=False)
    await ts_1.enable_timers()
    start_time = time.time()
    while (time.time() - start_time < election_timeout_max * 2
           and ts_1.operations.total != loop_limit):
        await asyncio.sleep(0.0001)
    assert ts_1.operations.total == loop_limit        
    await cluster.stop_auto_comms()
    logger.debug('------------------------ Tardy follower caught up ---')

async def test_empty_log_2(cluster_maker):
    """
    Tests that a follower crash and recovery with an empty log eventually leads to a successful
    sync with the rest of the cluster.

    Test starts with normal election, then a foller is crashed and restarted with
    an empty log. The timer driven operations are then allowe to proceed
    until the follower is caught up and in sync.
    
    Timers are disabled during the first election, so during that phase
    all timer driven operations such as heartbeats are manually triggered.
    After the leader is crashed, timers are enabled and remain enabled for the rest
    of the test.
    
    """

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
    cluster.test_trace.start_subtest("Initial election, normal with timers disabled",
                                     test_path_str=str('/'.join(Path(__file__).parts[-2:])),
                                     test_doc_string=test_empty_log_2.__doc__)
    await cluster.start()
    await ts_1.start_campaign()
    await cluster.run_election()
    
    assert ts_1.get_role_name() == "LEADER"
    assert ts_2.get_leader_uri() == uri_1
    assert ts_3.get_leader_uri() == uri_1
    logger.info('------------------------ Election done')

    cluster.test_trace.start_subtest("Node 1 is leader, crashing and recovering node 2 with an empty log then waiting for it to catch up")
    # Now "crash" the a follower and clear its log
    await ts_2.simulate_crash()
    await ts_2.recover_from_crash(save_log=False)
    assert await ts_2.log.get_last_index() == 0
    await cluster.start_auto_comms()
    await ts_1.enable_timers()
    logger.info('------------------------ ts_2 "crash" and restart done')
    start_time = time.time()
    while (time.time() - start_time < heartbeat_period * 5 
           and await ts_2.log.get_last_index() != 1):
        await asyncio.sleep(0.0001)
    assert await ts_2.log.get_last_index() == 1
    await cluster.stop_auto_comms()
    logger.debug('------------------------ Follower caught up ---')

