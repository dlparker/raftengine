#!/usr/bin/env python
import asyncio
import logging
import pytest
import time
from pathlib import Path

from dev_tools.sequences import SNormalElection, SNormalCommand
from dev_tools.log_control import setup_logging
from dev_tools.pausing_cluster import cluster_maker
from dev_tools.features import FeatureRegistry

log_control = setup_logging()
logger = logging.getLogger("test_code")
registry = FeatureRegistry.get_registry()

async def test_partition_1(cluster_maker):
    """
    This is a basic test of network partitioning and recovery. Five nodes are
    started and brought into sync after and election. Then two nodes are
    configured to be on a different simulated network partition than the
    leader and two other nodes. This means that the leader still has a quorum
    and can continue to advance the log. So, the leader runs a couple of commands
    after partition and we check to see that the reachable nodes get updated
    properly. We also check that the unreachable ones don't, but that is more
    about testing the simulation rather than any raft feature.

    One these verifications are done, the isolated nodes are configured to rejoin
    the main network and the leader is prodded to do a heartbeat broadcast. Some
    fiddly simulation control bits are used to single step through the message
    delivery process so as to verify that each heartbeat message reaches
    the right target and the target does the correct state ops and encodes
    the right reply. The rejoined nodes should walk through the state changes
    until they have correctly replicated the leader's log and the simulation
    state machine's final state.

    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """
    
    # Feature definitions for basic network partition with recovery
    f_election = registry.get_raft_feature("leader_election", "all_yes_votes.with_pre_vote")
    f_command_execution = registry.get_raft_feature("state_machine_command", "all_in_sync")
    f_minority_isolation = registry.get_raft_feature("network_partition", "follower_isolation")
    f_majority_continues = registry.get_raft_feature("network_partition", "majority_partition_operation")
    f_partition_healing = registry.get_raft_feature("network_partition", "post_partition_recovery")
    f_log_catchup = registry.get_raft_feature("log_replication", "log_catchup")
    
    cluster = cluster_maker(5)
    cluster.set_configs()

    uri_1, uri_2, uri_3, uri_4, uri_5 = cluster.node_uris
    ts_1, ts_2, ts_3, ts_4, ts_5 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3, uri_4, uri_5]]

    await cluster.test_trace.define_test("Testing basic network partitioning and recovery", logger=logger)
    
    spec = dict(used=[f_election], tested=[])
    await cluster.test_trace.start_test_prep("Normal election with 5 nodes", features=spec)
    await cluster.start()
    await ts_1.start_campaign()

    sequence = SNormalElection(cluster, 1)
    await cluster.run_sequence(sequence)
    

    assert ts_1.get_role_name() == "LEADER"
    assert ts_2.get_leader_uri() == uri_1
    assert ts_3.get_leader_uri() == uri_1
    assert ts_4.get_leader_uri() == uri_1
    assert ts_5.get_leader_uri() == uri_1

    logger.info('-------- Election done, saving a command record')

    spec = dict(used=[f_command_execution], tested=[])
    await cluster.test_trace.start_subtest("Run one command, normal sequence till leader commit, check follower's final state", features=spec)
    
    await cluster.start_auto_comms()
    sequence2 = SNormalCommand(cluster, "add 1", 1)
    command_result = await cluster.run_sequence(sequence2)
    assert command_result is not None
    assert command_result.result is not None
    assert ts_1.operations.total == 1
    assert ts_2.operations.total == 1
    assert ts_3.operations.total == 1
    assert ts_4.operations.total == 1
    assert ts_5.operations.total == 1
    any = True
    while any:
        await asyncio.sleep(0.0001)
        any = False
        for uri,node in cluster.nodes.items():
            if len(node.in_messages) > 0 or len(node.out_messages) > 0:
                any = True
                break

    logger.info('--------- Everbody has first record, partitioning network to isolate nodes 2 and 3')

    spec = dict(used=[], tested=[f_minority_isolation])
    await cluster.test_trace.start_subtest("Partitioning the network to isolate nodes 2 and 3", features=spec)
    # the partition sets were chosen to make the traces easier to follow
    part1 = {uri_1: ts_1,
             uri_4: ts_4,
             uri_5: ts_5}
    part2 = {uri_2: ts_2,
             uri_3: ts_3}
    await cluster.split_network([part1, part2])
    
    logger.info('--------- Everbody has first record, partition done, repeating command')
    
    spec = dict(used=[f_minority_isolation], tested=[f_majority_continues])
    await cluster.test_trace.start_subtest("Running two commands, only nodes 1, 4 and 5 should participate", features=spec)
    sequence3 = SNormalCommand(cluster, "add 1", 1)
    command_result = await cluster.run_sequence(sequence3)
    assert command_result is not None
    assert command_result.result is not None
    assert ts_1.operations.total == 2
    assert ts_2.operations.total == 1
    assert ts_3.operations.total == 1
    assert ts_4.operations.total == 2
    assert ts_5.operations.total == 2
    logger.info('--------- Main partition has update, doing it again')
    sequence4 = SNormalCommand(cluster, "add 1", 1)
    command_result = await cluster.run_sequence(sequence4)
    assert command_result is not None
    assert command_result.result is not None
    assert ts_1.operations.total == 3
    assert ts_2.operations.total == 1
    assert ts_3.operations.total == 1
    assert ts_4.operations.total == 3
    assert ts_5.operations.total == 3

    any = True
    while any:
        await asyncio.sleep(0.0001)
        any = False
        for uri,node in cluster.nodes.items():
            if len(node.in_messages) > 0 or len(node.out_messages) > 0:
                any = True
                break

    logger.info('--------- Now healing partition and looking for sync ----')
    await cluster.stop_auto_comms()
    
    spec = dict(used=[f_majority_continues], tested=[f_partition_healing])
    await cluster.test_trace.start_subtest("Healing network, nodes 2 and 3 will now be reachable from leader node 1, sending heartbeats", features=spec)
    await cluster.unsplit()
    logger.info('--------- Sending heartbeats ----')
    await ts_1.send_heartbeats()
    # gonna send four
    sends = []
    for i in range(4):
        msg = await ts_1.do_next_out_msg()
        assert msg  is not None
        if msg.receiver == uri_4:
            ts_4_msg = msg
        if msg.receiver == uri_5:
            ts_5_msg = msg
    # let the up to date node do their heartbeat sequence
    assert await ts_4.do_next_in_msg() is not None
    assert await ts_4.do_next_out_msg() is not None
    assert await ts_5.do_next_in_msg() is not None
    assert await ts_5.do_next_out_msg() is not None
    # get two back, now those guys are out of the way
    replys = []
    for i in range(2):
        msg = await ts_1.do_next_in_msg()
        assert msg is not None
        assert msg.sender in [uri_4, uri_5]
    # so know we can let are behind the times ones respond

    spec = dict(used=[f_partition_healing], tested=[f_log_catchup])
    await cluster.test_trace.start_subtest("Nodes 4 and 5 have processed heartbeats, now nodes 2 and 3 should do so", features=spec)
    logger.debug('--------- 2 and 3 should be pending, doing message sequence on one then other ')
    for node in [ts_2, ts_3]:
        msg = await node.do_next_in_msg() 
        assert msg is not None
        msg = await node.do_next_out_msg() 
        assert msg is not None
        # leader gets the news that the node needs catchup, sends them
        catchup_request = await ts_1.do_next_in_msg()
        assert catchup_request.sender == node.uri
        assert catchup_request is not None
        assert catchup_request.success == False
        assert catchup_request.maxIndex == 2 # first is start term
        # this will be a backdown
        backdown1 = await ts_1.do_next_out_msg()
        assert backdown1 is not None
        assert backdown1.commitIndex == 4
        assert backdown1.prevLogIndex == 2
        # let the leader collect t
        assert await node.do_next_in_msg() is not None
        # and send a response, should match
        catchup_request2 = await node.do_next_out_msg()
        # let leader get it
        assert await ts_1.do_next_in_msg() is not None
        # now let leader send next
        catchup_respose = await ts_1.do_next_out_msg()
        # now have the node accept it
        assert await node.do_next_in_msg() is not None
        # and send a response, should say we're good to end
        catchup_request3 = await node.do_next_out_msg()
        assert catchup_request3.success == True
        assert catchup_request3.maxIndex == 4
        # let the leader collect t
        assert await ts_1.do_next_in_msg() is not None

    # give time for applying command    
    await asyncio.sleep(0.01)


    assert ts_2.operations.total == 3
    assert ts_3.operations.total == 3
    await cluster.test_trace.end_subtest()

async def test_partition_2_leader(cluster_maker):
    """
    Tests that the correct state results when a network partitions and leaves the leader
    isolated from the majority of the cluster nodes, and then rejoins the majority network.

    This is verified by completing an election, and running a state machine command to
    establish replicated state.

    Then the leader is partitioned, then a new election is held. After completing the election,
    a new state machine command is executed, which should succeed because the
    new leader has a quorum.

    After that log record is replicated, the old leader is allowed to rejoin the majority network.

    The old leader is prodded to send out a heartbeat. This will get rejections and the old
    leader should notice the new term in the responses. When it does, it will resign.

    Finally a heartbeat sequence is executed so that the old leader sees then new
    log state from the new leader, and it will tell the leader to catch it up with
    an additional append_entries message.

    When all that is done, the state machine state at the old leader should match the replicated
    state in the other nodes.
    
    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """
    
    # Feature definitions for leader isolation and recovery
    f_election = registry.get_raft_feature("leader_election", "all_yes_votes.with_pre_vote")
    f_leader_isolation = registry.get_raft_feature("network_partition", "leader_isolation")
    f_automated_election = registry.get_raft_feature("leader_election", "automated_election_process")
    f_majority_continues = registry.get_raft_feature("network_partition", "majority_partition_operation")
    f_command_execution = registry.get_raft_feature("log_replication", "command_execution")
    f_network_partitioning = registry.get_raft_feature("test_infrastructure", "network_partitioning")
    f_quorum_checking = registry.get_raft_feature("leader_election", "quorum_checking")
    f_partition_healing = registry.get_raft_feature("network_partition", "post_partition_recovery")
    f_split_brain_resolution = registry.get_raft_feature("network_partition", "split_brain_resolution")
    f_post_partition_recovery = registry.get_raft_feature("network_partition", "post_partition_recovery")
    f_leader_demotion = registry.get_raft_feature("leader_election", "leader_demotion")
    f_heartbeat_processing = registry.get_raft_feature("log_replication", "heartbeat_processing")
    
    cluster = cluster_maker(3)
    cluster.set_configs()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]
    await cluster.test_trace.define_test("Testing leader isolation and recovery in network partition", logger=logging.getLogger("test_code"))
    
    spec = dict(used=[f_election], tested=[])
    await cluster.test_trace.start_test_prep("Normal election with 3 nodes", features=spec)
    await cluster.start()
    await ts_1.start_campaign()
    await cluster.run_election()
    
    assert ts_1.get_role_name() == "LEADER"
    assert ts_2.get_leader_uri() == uri_1
    assert ts_3.get_leader_uri() == uri_1
    logger = logging.getLogger(__name__)
    # Section 2: Command execution to establish state before partition
    spec = dict(used=[f_command_execution], tested=[])
    await cluster.test_trace.start_subtest("Election complete, running a command ", features=spec)
    logger.info('------------------------ Election done')
    logger.info('---------!!!!!!! starting comms')
    command_result = await cluster.run_command("add 1", 1)
    assert ts_2.operations.total == 1
    assert ts_3.operations.total == 1
    logger.debug('------------------------ Correct command done')

    # Now we want to block all messages from the leader, then
    # trigger a follower to hold an election, wait for it to
    # win, then unblock the old leader, and then let the
    # ex-leader send a heartbeat. The result of this should
    # tell the ex-leader who the new leader is, and it should
    # demote to follower. Another heartbeat from the real
    # leader and it should update everything.

    
    # Section 3: Leader isolation from majority partition
    spec = dict(used=[f_network_partitioning], tested=[f_leader_isolation])
    await cluster.test_trace.start_subtest("Command complete, partitioning leader ", features=spec)
    part1 = {uri_1: ts_1}
    part2 = {uri_2: ts_2,
             uri_3: ts_3}
    await cluster.split_network([part1, part2])

    logger.info('---------!!!!!!! stopping comms')
    # Section 4: Majority partition election with new leader
    spec = dict(used=[f_automated_election], tested=[f_majority_continues])
    await cluster.test_trace.start_subtest("Holding new election, node 2 will win ", features=spec)
    await ts_2.start_campaign(authorized=True)
    await cluster.run_election()
    assert ts_1.get_role_name() == "LEADER"
    assert ts_2.get_role_name() == "LEADER"
    assert ts_3.get_leader_uri() == uri_2
    # Section 5: Split brain scenario - new leader operates with quorum
    spec = dict(used=[f_command_execution], tested=[f_split_brain_resolution])
    await cluster.test_trace.start_subtest("Both node 1 and node 2 think they are leaders, but only node 2 has a quorum, running command there ", features=spec)
    command_result = await cluster.run_command("add 1", 1)
    assert ts_2.operations.total == 2
    await cluster.deliver_all_pending()
    # Section 6: Network partition healing
    spec = dict(used=[f_network_partitioning], tested=[f_partition_healing])
    await cluster.test_trace.start_subtest("Letting old leader re-join majority network", features=spec)
    await cluster.unsplit()
    logger.info('------------------------ Sending heartbeats from out of date leader')
    # Section 7: Old leader detection of new term and resignation
    spec = dict(used=[f_heartbeat_processing], tested=[f_leader_demotion])
    await cluster.test_trace.start_subtest("Sending heartbeats from old leader, should resign", features=spec)
    await ts_1.send_heartbeats()
    await cluster.deliver_all_pending()
    assert ts_1.get_role_name() == "FOLLOWER"
    # let ex-leader catch up
    # Section 8: Log synchronization and cluster state consistency
    spec = dict(used=[f_heartbeat_processing], tested=[f_post_partition_recovery])
    await cluster.test_trace.start_subtest("Sending heartbeats from new leader, sould catch up old leader", features=spec)
    await ts_2.send_heartbeats()
    await cluster.deliver_all_pending()
    assert ts_1.operations.total == 2
    await cluster.test_trace.end_subtest()
    logger.info('------------------------ Leadership change correctly detected')


async def test_partition_3_leader(cluster_maker):
    """
    Tests that the correct state results when a network partitions and leaves the leader
    isolated from the majority of the cluster nodes and the leader detects isolation
    via check quorum logic..

    This is verified by completing an election, and running a state machine command to
    establish replicated state.

    Then the leader is partitioned, a new election is run.

    Next the timers are enabled on the old leader, then a period of time longer than the election
    timeout max value is allowed to pass, then the old leader's state is
    checked to ensure that it has resigned.

    Then, just for completeness, the partion is healed and the leader is checked
    to see if it is up to date. It should have the term start record for the new term in the log.
    
    """
    
    # Feature definitions - leader quorum checking and self-resignation
    f_leader_isolation = registry.get_raft_feature("network_partition", "leader_isolation")
    f_automated_election = registry.get_raft_feature("leader_election", "automated_election_process")
    f_command_execution = registry.get_raft_feature("log_replication", "command_execution")
    f_network_partitioning = registry.get_raft_feature("test_infrastructure", "network_partitioning")
    f_quorum_checking = registry.get_raft_feature("leader_election", "quorum_checking")
    f_leader_self_resignation = registry.get_raft_feature("leader_election", "leader_self_resignation")
    f_timer_operations = registry.get_raft_feature("test_infrastructure", "timer_operations")
    f_partition_healing = registry.get_raft_feature("network_partition", "post_partition_recovery")
    
    cluster = cluster_maker(3)
    heartbeat_period = 0.001
    election_timeout_min = 0.009
    election_timeout_max = 0.011
    config = cluster.build_cluster_config(heartbeat_period=heartbeat_period,
                                          election_timeout_min=election_timeout_min, 
                                          election_timeout_max=election_timeout_max)
    cluster.set_configs(config)
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]
    logger = logging.getLogger(__name__)
    await cluster.test_trace.define_test("Testing leader isolation with check quorum logic", logger=logger)
    
    # Section 1: Initial election establishment
    spec = dict(used=[f_automated_election], tested=[])
    await cluster.test_trace.start_test_prep("Normal election", features=spec)
    await cluster.start()
    await ts_1.start_campaign()
    await cluster.run_election()
    
    assert ts_1.get_role_name() == "LEADER"
    assert ts_2.get_leader_uri() == uri_1
    assert ts_3.get_leader_uri() == uri_1
    logger = logging.getLogger(__name__)
    # Section 2: Leader isolation from majority partition
    spec = dict(used=[f_network_partitioning], tested=[f_leader_isolation])
    await cluster.test_trace.start_subtest("Election complete, partitioning leader", features=spec)
    logger.info('------------------------ Election done, partitioning')

    part1 = {uri_1: ts_1}
    part2 = {uri_2: ts_2,
             uri_3: ts_3}
    await cluster.split_network([part1, part2])

    # Section 3: Majority partition election with new leader
    spec = dict(used=[f_automated_election], tested=[])
    await cluster.test_trace.start_subtest("Holding new election, node 2 will win ", features=spec)
    await ts_2.start_campaign(authorized=True)
    await cluster.run_election()
    assert ts_1.get_role_name() == "LEADER"
    assert ts_2.get_role_name() == "LEADER"
    assert ts_3.get_leader_uri() == uri_2
    await cluster.deliver_all_pending()
    # Section 4: Isolated leader quorum checking and self-resignation
    spec = dict(used=[f_timer_operations], tested=[f_quorum_checking, f_leader_self_resignation])
    await cluster.test_trace.start_subtest("Both node 1 and node 2 think they are leaders, node 2 has quorum, enabling timers on node 1 and waiting  ", features=spec)

    await cluster.start_auto_comms()
    await ts_1.enable_timers() # resets
    wait_time = (election_timeout_max + heartbeat_period) * 2.0
    start_time = time.time()
    while time.time() - start_time < wait_time and ts_1.get_role_name() == "LEADER":
        await asyncio.sleep(heartbeat_period/4.0)
    assert ts_1.get_role_name() != "LEADER"
    
    # Section 5: Network healing and log synchronization
    spec = dict(used=[f_network_partitioning, f_timer_operations], tested=[f_partition_healing])
    await cluster.test_trace.start_subtest("Old leader resigned on check quorum, healing network and waiting for it to rejoin", features=spec)
    await ts_2.enable_timers() # resets
    await ts_3.enable_timers() # resets
    await cluster.unsplit()
    await cluster.start_auto_comms()
    wait_time = (election_timeout_max + heartbeat_period) * 2.0
    expected_index = await ts_2.log.get_last_index()
    start_time = time.time()
    while time.time() - start_time < wait_time and await ts_1.log.get_last_index() != expected_index:
        await asyncio.sleep(heartbeat_period/4.0)
        
    assert await ts_1.log.get_last_index() == expected_index
    assert ts_1.get_leader_uri() == uri_2
    await cluster.test_trace.end_subtest()
    logger.info('------------------------ Leadership change correctly detected')
    
async def test_partition_3_follower(cluster_maker):
    """
    Tests that the correct state results when a network partitions and leaves a follower
    isolated from the majority of the cluster nodes and the leader runs check quorum logic.
    The leader should continue and not resign.

    This is verified by completing an election, and running a state machine command to
    establish replicated state.

    Then the follower is partitioned.

    Next the timers are enabled on the all the nodes and a period greater than the
    timeout max value is allowed to pass. The leader is checked to see that it hasn't
    resigned.

    """
    
    # Feature definitions - follower isolation with leader quorum maintenance
    f_follower_isolation = registry.get_raft_feature("network_partition", "follower_isolation")
    f_automated_election = registry.get_raft_feature("leader_election", "automated_election_process")
    f_command_execution = registry.get_raft_feature("log_replication", "command_execution")
    f_network_partitioning = registry.get_raft_feature("test_infrastructure", "network_partitioning")
    f_quorum_checking = registry.get_raft_feature("leader_election", "quorum_checking")
    f_leader_stability = registry.get_raft_feature("leader_election", "leader_stability")
    f_timer_operations = registry.get_raft_feature("test_infrastructure", "timer_operations")
    f_majority_operations = registry.get_raft_feature("network_partition", "majority_partition_operation")
    
    cluster = cluster_maker(3)
    heartbeat_period = 0.001
    election_timeout_min = 0.009
    election_timeout_max = 0.011
    config = cluster.build_cluster_config(heartbeat_period=heartbeat_period,
                                          election_timeout_min=election_timeout_min, 
                                          election_timeout_max=election_timeout_max)
    cluster.set_configs(config)
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]
    logger = logging.getLogger(__name__)
    await cluster.test_trace.define_test("Testing follower isolation with leader quorum intact", logger=logger)
    
    # Section 1: Initial election establishment
    spec = dict(used=[f_automated_election], tested=[])
    await cluster.test_trace.start_test_prep("Normal election", features=spec)
    await cluster.start()
    await ts_1.start_campaign()
    await cluster.run_election()
    
    assert ts_1.get_role_name() == "LEADER"
    assert ts_2.get_leader_uri() == uri_1
    assert ts_3.get_leader_uri() == uri_1
    logger = logging.getLogger(__name__)
    # Section 2: Single follower isolation from majority
    spec = dict(used=[f_network_partitioning], tested=[f_follower_isolation])
    await cluster.test_trace.start_subtest("Election complete, partitioning one follower", features=spec)
    logger.info('------------------------ Election done, partitioning one follower')

    part1 = {uri_1: ts_1, uri_2: ts_2}
    part2 = {uri_3: ts_3}
    await cluster.split_network([part1, part2])

    # Section 3: Leader quorum maintenance despite follower isolation
    spec = dict(used=[f_timer_operations], tested=[f_quorum_checking, f_leader_stability, f_majority_operations])
    await cluster.test_trace.start_subtest("Leader has quorum, enabling timers and waiting long enough ", features=spec)

    await ts_1.enable_timers() # resets
    await ts_2.enable_timers() # resets
    await cluster.start_auto_comms()
    wait_time = (election_timeout_max + heartbeat_period) * 2.0
    start_time = time.time()
    while time.time() - start_time < wait_time:
        await asyncio.sleep(heartbeat_period/4.0)
    assert ts_1.get_role_name() == "LEADER"
    
    await cluster.test_trace.end_subtest()
