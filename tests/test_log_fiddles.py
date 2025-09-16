#!/usr/bin/env python
import asyncio
import logging
import time
from pathlib import Path
import pytest

from dev_tools.log_control import setup_logging
from dev_tools.features import FeatureRegistry
from dev_tools.pausing_cluster import cluster_maker

# Initialize feature registry
registry = FeatureRegistry.get_registry()

log_control = setup_logging()
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
    
    # Feature definitions - empty log recovery testing
    f_empty_log_recovery = registry.get_raft_feature("log_replication", "empty_log_recovery")
    f_crash_recovery = registry.get_raft_feature("system_reliability", "crash_recovery")
    f_automated_election = registry.get_raft_feature("leader_election", "automated_election_process")
    f_command_execution = registry.get_raft_feature("log_replication", "command_execution")
    f_timer_operations = registry.get_raft_feature("test_infrastructure", "timer_operations")
    f_log_catchup = registry.get_raft_feature("log_replication", "log_catchup")
    f_partial_election = registry.get_raft_feature("leader_election", "partial_election")
    
    cluster = cluster_maker(3)
    # do real timer values, but start in the usual disabled state.
    heartbeat_period=0.005
    election_timeout_min=0.09
    election_timeout_max=0.11
    config = cluster.build_cluster_config(heartbeat_period=heartbeat_period,
                                          election_timeout_min=election_timeout_min,
                                          election_timeout_max=election_timeout_max,
                                          use_pre_vote=False)
    cluster.set_configs(config)

    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]
    await cluster.test_trace.define_test("Testing leader recovery with empty log", logger=logger)
    
    # Section 1: Initial election establishment
    spec = dict(used=[f_automated_election], tested=[])
    await cluster.test_trace.start_test_prep("Normal election", features=spec)
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
    
    # Section 2: Log population with commands
    spec = dict(used=[f_command_execution], tested=[])
    await cluster.test_trace.start_subtest(f"Node 1 is leader, running {loop_limit} commands to fill log", features=spec)
    for i in range(loop_limit):
        command_result = await cluster.run_command("add 1", 1)
    await cluster.stop_auto_comms()

    assert ts_1.operations.total == loop_limit
    
    # Section 3: Leader crash, partial election, and empty log recovery
    spec = dict(used=[f_crash_recovery, f_partial_election, f_timer_operations], tested=[f_empty_log_recovery, f_log_catchup])
    await cluster.test_trace.start_subtest("Crashing leader node 1, clearing its log, restarting it, then letting timers run until catchup done", features=spec)
    
    # Now "crash" the leader, run an election, then have
    # the leader come up with an empty log
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
    await cluster.test_trace.define_test("Testing follower recovery with empty log", logger=logger)
    # Feature definitions - empty log recovery testing for follower
    f_empty_log_recovery = registry.get_raft_feature("log_replication", "empty_log_recovery")
    f_crash_recovery = registry.get_raft_feature("system_reliability", "crash_recovery")
    f_automated_election = registry.get_raft_feature("leader_election", "automated_election_process")
    f_timer_operations = registry.get_raft_feature("test_infrastructure", "timer_operations")
    f_log_catchup = registry.get_raft_feature("log_replication", "log_catchup")
    
    # Section 1: Initial election establishment
    spec = dict(used=[f_automated_election], tested=[])
    await cluster.test_trace.start_test_prep("Normal election", features=spec)
    await cluster.start()
    await ts_1.start_campaign()
    await cluster.run_election()
    
    assert ts_1.get_role_name() == "LEADER"
    assert ts_2.get_leader_uri() == uri_1
    assert ts_3.get_leader_uri() == uri_1
    logger.info('------------------------ Election done')

    # Section 2: Follower crash, empty log recovery, and automated catchup
    spec = dict(used=[f_crash_recovery, f_timer_operations], tested=[f_empty_log_recovery, f_log_catchup])
    await cluster.test_trace.start_subtest("Node 1 is leader, crashing and recovering node 2 with an empty log then waiting for it to catch up", features=spec)
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
