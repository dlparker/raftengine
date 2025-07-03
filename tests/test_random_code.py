#!/usr/bin/env python
import asyncio
import pytest
import logging

# Temp, remove when feature code is done
from dataclasses import dataclass, field
from typing import Optional
from dev_tools.triggers import WhenMessageOut, WhenMessageIn
from raftengine.messages.append_entries import AppendResponseMessage
from dev_tools.sequences import SPartialCommand
import time
import json 

from dev_tools.pausing_cluster import cluster_maker
from dev_tools.logging_ops import setup_logging
from dev_tools.features import FeatureRegistry
registry = FeatureRegistry.get_registry()


#setup_logging(extra_logging)
default_level='error'
#default_level='debug'
extra_logging = [dict(name="test_code", level="debug"), dict(name="Leader", level="debug"),
                 dict(name="Candidate", level="debug"),
                 dict(name="Follower", level="debug")]
                 
setup_logging(additions=extra_logging, default_level=default_level)
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


async def test_feature_defs_1(cluster_maker):
    """

    This runs the election happy path, everybody has same state, only one server
    runs for leader, everybody responds correctly. It is written
    using the most granular control provided by the PausingServer
    class, controlling the message movement steps directly (for
    the most part). The cluster is three nodes. Prevote is disabled for this test.

    If some basic error is introduced in the election related code, it will
    show up here with the most detail.

    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """
    f_election = registry.get_raft_feature("leader_election", "all_yes_votes.without_pre_vote")
    
    cluster = cluster_maker(3)
    config = cluster.build_cluster_config(use_pre_vote=False)
    cluster.set_configs(config)
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]

    await cluster.test_trace.define_test("Testing basic election happy path with 3 nodes, no pre-vote", logger=logger)
    spec = dict(used=[], tested=[f_election,])
    await cluster.test_trace.start_subtest("Transporting votes and append-entries unitl TERM_START is applied to all node",
                                           features=spec)
    await cluster.start()
    await ts_1.start_campaign()
    await cluster.run_election()
    
    assert ts_1.get_role_name() == "LEADER"
    assert ts_2.get_leader_uri() == uri_1
    assert ts_3.get_leader_uri() == uri_1
    logger.info('------------------------ Election done')

async def test_feature_defs_2(cluster_maker):
    """

    This runs the election happy path, with prevote enabled
    everybody has same state, only one server
    runs for leader, everybody responds correctly. It is written
    using the most granular control provided by the PausingServer
    class, controlling the message movement steps directly (for
    the most part). The cluster is three nodes.

    If some basic error is introduced in the election related code, it will
    show up here with the most detail.

    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """

    
    cluster = cluster_maker(3)
    config = cluster.build_cluster_config(use_pre_vote=True)
    cluster.set_configs(config)
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]

    await cluster.test_trace.define_test("Testing basic election happy path with 3 nodes, with PreVote", logger=logger)
    f_election = registry.get_raft_feature("leader_election", "all_yes_votes.with_pre_vote")
    spec = dict(used=[], tested=[f_election,])
    description = "Transporting pre-votes and votes until leader is elected, then "
    description += " transporting append-entries until TERM_START record is applied to all nodes."
    await cluster.test_trace.start_subtest(title="Doing message transport until new leader wins",
                                           description=description, features=spec)
    await cluster.start()
    
    await ts_1.start_campaign()
    await cluster.run_election()
    
    assert ts_1.get_role_name() == "LEADER"
    assert ts_2.get_leader_uri() == uri_1
    assert ts_3.get_leader_uri() == uri_1
    logger.info('------------------------ Election done')
    
async def test_feature_defs_3(cluster_maker):
    """
    This runs "commands" using highly granular control of test servers 
    so that basic bugs in the first command processing will show up at a detailed 
    level. It also tests that invalid command attempts receive the right response.
    Finally, it validates that crashing a follower, running a command, and recovering
    the follower eventually results in the crashed follower being in sync.
    
    The invalid commands tested are

    1. Sending a command request to a follower, which should result in a redirect
    2. Sending a command request to a candidate, which should result in a "retry", meaning
       that the cluster is currently unable to process commands, so a later retry is recommended

    The second test is performed by doing some artificial manipulation of the state of one of the
    nodes. It is pushed to become a candidate, which will caused it to increase its term. After
    the command is rejected with a retry, the candidate node is forced back to follower mode and
    its term is artificially adjusted down to zero so that it will accept the current leader.

    Because the term is now zero, when the former candidate node receives a heartbeat it
    will accept the current leader.

    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """

    
    cluster = cluster_maker(3)
    config = cluster.build_cluster_config(use_pre_vote=True)
    cluster.set_configs(config)
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]

    await cluster.test_trace.define_test("Testing state machine command propagation with 3 nodes", logger=logger)
    f_election = registry.get_raft_feature("leader_election", "all_yes_votes.with_pre_vote")
    spec = dict(used=[f_election,], tested=[])
    await cluster.test_trace.start_test_prep("Running normal election till fully replicated", features=spec)
    await cluster.start()
    await ts_1.start_campaign()
    await cluster.run_election()
    
    assert ts_1.get_role_name() == "LEADER"
    assert ts_2.get_leader_uri() == uri_1
    assert ts_3.get_leader_uri() == uri_1
    logger.info('------------------------ Election done')

    f_normal_command = registry.get_raft_feature("state_machine_command", "all_in_sync")
    spec = dict(used=[], tested=[f_normal_command])
    await cluster.test_trace.start_subtest("Run one command, normal sequence till leader commit", features=spec)
    await cluster.start_auto_comms()
    last_index = await ts_1.log.get_last_index()

    command_result = await ts_1.run_command("add 1")
    assert command_result.result is not None
    assert command_result.error is None
    assert ts_1.operations.total == 1
    # now we need to trigger a heartbeat so that
    # followers will see the commitIndex is higher
    # and apply and locally commit
    await cluster.stop_auto_comms()
    await ts_1.send_heartbeats()
    logger.info('------------------------ Leader has command completion, heartbeats going out')
    term = await ts_1.log.get_term()
    index = await ts_1.log.get_last_index()
    assert index == 2 # one for start term, one for command
    ts_1.set_trigger(WhenMessageIn(AppendResponseMessage.get_code()))
    ts_2.set_trigger(WhenMessageOut(AppendResponseMessage.get_code()))
    ts_3.set_trigger(WhenMessageOut(AppendResponseMessage.get_code()))
    await asyncio.gather(ts_1.run_till_triggers(),
                         ts_2.run_till_triggers(),
                         ts_3.run_till_triggers())
    ts_1.clear_triggers()
    ts_2.clear_triggers()
    ts_3.clear_triggers()
    assert ts_2.operations.total == 1
    assert ts_3.operations.total == 1
    assert await ts_2.log.get_term() == term
    assert await ts_2.log.get_last_index() == index
    assert await ts_3.log.get_term() == term
    assert await ts_3.log.get_last_index() == index
    logger.debug('------------------------ Correct command done')

    await cluster.stop_auto_comms()
    f_command_redirect = registry.get_raft_feature("state_machine_command", "request_redirect")
    spec = dict(used=[], tested=[f_command_redirect,])
    await cluster.test_trace.start_subtest("Trying to run command at follower, looking for redirect", features=spec)
    command_result = await ts_3.run_command("add 1")
    assert command_result.redirect == uri_1
    logger.debug('------------------------ Correct redirect (follower) done')
    
    await cluster.test_trace.start_subtest("Pushing one follower to candidate, then trying command to it, looking for retry")
    orig_term =  await ts_3.get_term() 
    await ts_3.do_leader_lost()
    assert ts_3.get_role_name() == "CANDIDATE"
    command_result = await ts_3.run_command("add 1")
    assert command_result.retry is not None
    logger.debug('------------------------ Correct retry (candidate) done')
    # get the leader to send it a heartbeat while it is a candidate
    await cluster.test_trace.start_test_prep("Pushing Leader to send heartbeats, after forcing candidate's term back down")
    # cleanup traces of attempt to start election
    logger.debug('------------------------ forcing candidate term down')
    ts_3.clear_all_msgs()
    await ts_3.log.set_term(orig_term)
    logger.debug('------------------------ sending heartbeats, should make candidate resign')
    await ts_1.send_heartbeats()
    await cluster.deliver_all_pending()
    assert ts_3.get_role_name() == "FOLLOWER"
    assert ts_3.get_leader_uri() == uri_1


    # Now simulate a crash of a follower,
    # and then do a couple of commands. Once the
    # commands are committed, let heartbeats go out
    # so the tardy follower will catch up

    f_command_min_nodes = registry.get_raft_feature("state_machine_command", "minimal_node_count")
    spec = dict(used=[], tested=[f_command_min_nodes,])
    await cluster.test_trace.start_subtest("Crashing one follower, then running command to ensure it works with only one follower",
                                           features=spec)
    await ts_3.simulate_crash()
    logger.debug('------------------------ Running command ---')
    sequence = SPartialCommand(cluster, "add 1", voters=[uri_1, uri_2])
    command_result = await cluster.run_sequence(sequence)
    assert ts_1.operations.total == 2
    sequence = SPartialCommand(cluster, "add 1", voters=[uri_1, uri_2])
    command_result = await cluster.run_sequence(sequence)
    assert ts_1.operations.total == 3
    start_time = time.time()
    while time.time() - start_time < 0.1 and ts_2.operations.total != 3:
        await asyncio.sleep(0.0001)
    assert ts_2.operations.total == 3
    await cluster.deliver_all_pending()
    await ts_1.send_heartbeats()
    await cluster.deliver_all_pending()
    f_rep_on_rejoin = registry.get_raft_feature("state_machine_command", "apply_on_delayed_replication")
    f_slow_backdown = registry.get_raft_feature("log_replication", "slow_follower_backdown")
    spec = dict(used=[f_slow_backdown,], tested=[f_rep_on_rejoin,])
    await cluster.test_trace.start_subtest("Recovering follower, then pushing hearbeat to get it to catch up",
                                           features=spec)
    logger.debug('------------------------ Unblocking, doing hearbeats, should catch up ---')
    await ts_3.recover_from_crash()
    await ts_1.send_heartbeats()
    await cluster.start_auto_comms()
    start_time = time.time()
    while time.time() - start_time < 0.1 and ts_1.operations.total != 3:
        await asyncio.sleep(0.0001)
    assert ts_3.operations.total == 3
    await cluster.stop_auto_comms()
    await cluster.deliver_all_pending()
    await cluster.deliver_all_pending()
    logger.debug('------------------------ Tardy follower caught up ---')
    await cluster.test_trace.end_subtest()
    
