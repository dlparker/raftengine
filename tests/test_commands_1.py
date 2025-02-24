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
from dev_tools.servers import SNormalElection, SNormalCommand, SPartialElection, SPartialCommand
from dev_tools.servers import setup_logging, log_config

#extra_logging = [dict(name="test_code", level="debug"), dict(name="Triggers", level="debug")]
#extra_logging = [dict(name="test_code", level="debug"), ]
#log_config = setup_logging(extra_logging, default_level="debug")
log_config = setup_logging()
logger = logging.getLogger("test_code")

async def test_command_1(cluster_maker):
    """ This runs commands using highly granular control of test servers 
    so that basic bugs in the first command processing will show up at a detailed 
    level. Timers are disabled.
    """
    cluster = cluster_maker(3)
    cluster.set_configs()

    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]
    logger = logging.getLogger(__name__)
    await cluster.start()
    await ts_3.hull.start_campaign()
    sequence = SNormalElection(cluster, 1)
    await cluster.run_sequence(sequence)
    
    assert ts_3.hull.get_state_code() == "LEADER"
    assert ts_1.hull.state.leader_uri == uri_3
    assert ts_2.hull.state.leader_uri == uri_3
    logger = logging.getLogger(__name__)
    logger.info('------------------------ Election done')
    await cluster.start_auto_comms()

    command_result = await ts_3.hull.run_command("add 1")
    assert command_result.result is not None
    assert command_result.error is None
    assert ts_3.operations.total == 1
    # now we need to trigger a heartbeat so that
    # followers will see the commitIndex is higher
    # and apply and locally commit
    await cluster.stop_auto_comms()
    await ts_3.hull.state.send_heartbeats()
    logger.info('------------------------ Leader has command completion, heartbeats going out')
    term = await ts_3.hull.log.get_term()
    index = await ts_3.hull.log.get_last_index()
    assert index == 2 # one for start term, one for command
    ts_1.set_trigger(WhenMessageOut(AppendResponseMessage.get_code()))
    ts_2.set_trigger(WhenMessageOut(AppendResponseMessage.get_code()))
    ts_3.set_trigger(WhenMessageIn(AppendResponseMessage.get_code()))
    await asyncio.gather(ts_1.run_till_triggers(),
                         ts_2.run_till_triggers(),
                         ts_3.run_till_triggers())
    ts_1.clear_triggers()
    ts_2.clear_triggers()
    ts_3.clear_triggers()
    assert ts_1.operations.total == 1
    assert ts_2.operations.total == 1
    assert await ts_1.hull.log.get_term() == term
    assert await ts_1.hull.log.get_last_index() == index
    assert await ts_2.hull.log.get_term() == term
    assert await ts_2.hull.log.get_last_index() == index
    logger.debug('------------------------ Correct command done')

    await cluster.stop_auto_comms()
    command_result = await ts_1.hull.run_command("add 1")
    assert command_result.redirect == uri_3
    logger.debug('------------------------ Correct redirect (follower) done')
    
    orig_term =  await ts_1.hull.get_term() 
    await ts_1.hull.state.leader_lost()
    assert ts_1.hull.get_state_code() == "CANDIDATE"
    command_result = await ts_1.hull.run_command("add 1")
    assert command_result.retry is not None
    logger.debug('------------------------ Correct retry (candidate) done')
    ts_1.clear_all_msgs()
    await ts_1.log.set_term(orig_term - 1)
    # get the leader to send it a heartbeat while it is a candidate
    await ts_3.hull.state.send_heartbeats()
    await cluster.deliver_all_pending()
    # cleanup traces of attempt to start election
    await ts_1.log.set_term(orig_term)

    await ts_1.hull.demote_and_handle()
    await ts_3.hull.state.send_heartbeats()
    await cluster.deliver_all_pending()
    print(await ts_1.dump_stats())
    await asyncio.sleep(0.01)
    assert ts_1.hull.get_state_code() == "FOLLOWER"
    assert ts_1.hull.state.leader_uri == uri_3


    # Now block a follower's messages, like it crashed,
    # and then do a couple of commands. Once the
    # commands are committed, let heartbeats go out
    # so the tardy follower will catch up

    ts_1.block_network()
    logger.debug('------------------------ Running command ---')
    sequence = SPartialCommand(cluster, "add 1", voters=[uri_2, uri_3])
    command_result = await cluster.run_sequence(sequence)
    assert ts_3.operations.total == 2
    sequence = SPartialCommand(cluster, "add 1", voters=[uri_2, uri_3])
    command_result = await cluster.run_sequence(sequence)
    assert ts_3.operations.total == 3
    start_time = time.time()
    while time.time() - start_time < 0.1 and ts_2.operations.total != 3:
        await asyncio.sleep(0.0001)
    assert ts_2.operations.total == 3

    logger.debug('\n\n\n------------------------ Unblocking, doing hearbeats, should catch up ---\n\n\n')
    ts_1.unblock_network() # default is discard messages, lets do that
    await ts_3.hull.state.send_heartbeats()
    await cluster.start_auto_comms()
    start_time = time.time()
    while time.time() - start_time < 0.1 and ts_1.operations.total != 3:
        await asyncio.sleep(0.0001)
    assert ts_1.operations.total == 3
    await cluster.stop_auto_comms()
    logger.debug('------------------------ Tardy follower caught up ---')

async def test_command_sqlite_1(cluster_maker):
    from dev_tools.sqlite_log import SqliteLog
    cluster = cluster_maker(3, use_log=SqliteLog)
    cluster.set_configs()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]
    logger = logging.getLogger(__name__)
    await cluster.start()
    await ts_3.hull.start_campaign()

    await cluster.run_election()
    assert ts_3.hull.get_state_code() == "LEADER"
    assert ts_1.hull.state.leader_uri == uri_3
    assert ts_2.hull.state.leader_uri == uri_3
    logger = logging.getLogger(__name__)
    logger.info('------------------------ Election done')
    await cluster.start_auto_comms()

    command_result = await cluster.run_command("add 1", 1)
    
    assert ts_1.operations.total == 1
    assert ts_2.operations.total == 1
    assert ts_3.operations.total == 1
    term = await ts_3.hull.log.get_term()
    index = await ts_3.hull.log.get_last_index()
    assert index == 2 # first index will be the start term record
    assert await ts_1.hull.log.get_term() == term
    assert await ts_1.hull.log.get_last_index() == index
    assert await ts_2.hull.log.get_term() == term
    assert await ts_2.hull.log.get_last_index() == index
    logger.debug('------------------------ Correct command done')
    rec_1 = await ts_1.hull.log.read(index)
    rec_2 = await ts_2.hull.log.read(index)
    rec_3 = await ts_3.hull.log.read(index)
    assert rec_1.result == rec_2.result 
    assert rec_1.result == rec_3.result
    new_rec = LogRec.from_dict(rec_1.__dict__)
    assert new_rec.result == rec_1.result
    await cluster.stop_auto_comms()
    
async def double_leader_inner(cluster, discard):
    cluster.set_configs()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]
    logger = logging.getLogger(__name__)
    await cluster.start()
    await ts_1.hull.start_campaign()
    await cluster.run_election()
    
    assert ts_1.hull.get_state_code() == "LEADER"
    assert ts_2.hull.state.leader_uri == uri_1
    assert ts_3.hull.state.leader_uri == uri_1
    logger = logging.getLogger(__name__)
    logger.info('------------------------ Election done')
    logger.info('---------!!!!!!! starting comms')
    command_result = await cluster.run_command("add 1", 1)
    assert ts_2.operations.total == 1
    assert ts_3.operations.total == 1
    logger.debug('------------------------ Correct command done')

    # Now we want to block all messages from the leader, then
    # trigger a follower to hold an election, wait for it to
    # win, then unblock the old leader, and then try another
    # command. The leader should figure out it doesn't lead
    # anymore and give back a redirect

    logger.info('---------!!!!!!! stopping comms')
    await cluster.stop_auto_comms()
    ts_1.block_network()
    logger.info('------------------ isolated leader, starting new election')
    await ts_2.hull.start_campaign()
    await cluster.run_election()
    assert ts_1.hull.get_state_code() == "LEADER"
    assert ts_2.hull.get_state_code() == "LEADER"
    assert ts_3.hull.state.leader_uri == uri_2

    if discard:
        # will discard the messages that were blocked so
        # leader gets missed messages
        ts_1.unblock_network()
        logger.info('---------!!!!!!! starting comms')
        await cluster.start_auto_comms()
    else:
        # will deliver blocked message
        ts_1.unblock_network(deliver=True)
        await cluster.start_auto_comms()
        
    logger.debug('------------------ Command AppendEntries should get rejected -')

    command_result = await cluster.run_command("add 1", timeout=0.1)
    assert command_result is not None
    assert command_result.redirect == uri_2
    logger.info('---------!!!!!!! stopping comms')
    await cluster.stop_auto_comms()
    logger.info('------------------------ Correct redirect (follower) done')
    
async def test_command_2_leaders_1(cluster_maker):
    cluster = cluster_maker(3)
    await double_leader_inner(cluster, True)    

async def test_command_2_leaders_2(cluster_maker):
    cluster = cluster_maker(3)
    await double_leader_inner(cluster, False)    
    
async def test_command_after_heal_1(cluster_maker):
    # The goal is for one a candidate to receive an
    # append entries message from a lower of a lower term.
    # This can happen when a network partition resolves
    # before the pre-partition leader has resigned, where
    # the partition leaves the old leader connected to
    # less than half the cluster, and the other side of the
    # partition completes a new election before the
    # partition heals. 
    #
    # Likely? I doubt it. Possible? Certainly, so code needs
    # to exist to handle it (in the candidate state) and that
    # path needs to be tested.
    # 

    cluster = cluster_maker(3)
    cluster.set_configs()

    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]
    logger = logging.getLogger(__name__)
    await cluster.start()
    await ts_1.hull.start_campaign()
    await cluster.run_election()
    
    assert ts_1.hull.get_state_code() == "LEADER"
    assert ts_2.hull.state.leader_uri == uri_1
    assert ts_3.hull.state.leader_uri == uri_1
    logger = logging.getLogger(__name__)
    logger.info('-------------- Election done, about to split network leaving leader %s isolated ', uri_1)
    command_result = await cluster.run_command(command="add 1", timeout=1)
    assert ts_1.operations.total == 1
    assert ts_2.operations.total == 1
    assert ts_3.operations.total == 1
    logger.debug('------------------------ Correct command done')

    # now simulate a split newtork with the leader
    # getting isolated, then trigger one of the followers
    # to start and election
    await cluster.stop_auto_comms()
    part1 = {uri_1: ts_1}
    part2 = {uri_2: ts_2,
             uri_3: ts_3}
    cluster.split_network([part1, part2])

    logger.info('-------------- Split network done, expecting election of %s', uri_2)
    # now ts_2 and ts_3 are alone, have ts_2
    # get elected
    await ts_2.hull.state.leader_lost()
    await cluster.run_election()
    assert ts_2.hull.get_state_code() == "LEADER"
    assert ts_3.hull.state.leader_uri == uri_2
    last_term = await ts_2.hull.log.get_term()
    logger.info('-------------- %s elected, unspliting the network', uri_2)
    cluster.unsplit()
    assert ts_1.hull.get_state_code() == "LEADER"
    logger.info('-------------- %s reconneted, thinks it is still leader', uri_1)
    
    logger.info('-------------- Forcing %s to candidate, but not allowing any messages out', uri_2)
    ts_2.block_network()
    await ts_2.hull.demote_and_handle(None)
    assert ts_2.hull.get_state_code() == "FOLLOWER"
    await ts_2.hull.start_campaign()
    assert ts_2.hull.get_state_code() == "CANDIDATE"
    
    logger.info('-------------- telling old leader %s to send heartbeats, %s should reject in candidate',
                uri_1, uri_2)

    assert ts_1.hull.get_state_code() == "LEADER"
    # don't deliver vote requests, it will complicate things
    ts_2.unblock_network()
    await ts_1.hull.state.send_heartbeats()
    logger.info('-------------- old leader %s sent heartbeats, %s unblocked',
                uri_1, uri_2)
    await cluster.deliver_all_pending()

    # don't know how the election will turn out for sure, probably ts_2 will win
    # important thing is that ts_1 responded properly to higher term in response,
    # meannig that candidate reply did its thing
    assert await ts_1.hull.log.get_term() > last_term
    
async def test_follower_explodes_in_command(cluster_maker):
    cluster = cluster_maker(3)
    cluster.set_configs()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]
    logger = logging.getLogger(__name__)
    await cluster.start()
    await ts_1.hull.start_campaign()

    await cluster.run_election()
    assert ts_1.hull.get_state_code() == "LEADER"
    assert ts_1.hull.state.leader_uri == uri_1
    assert ts_2.hull.state.leader_uri == uri_1
    logger = logging.getLogger(__name__)
    logger.info('------------------------ Election done')

    command_result = await cluster.run_command("add 1", 1)
    assert ts_1.operations.total == 1
    assert ts_2.operations.total == 1
    assert ts_3.operations.total == 1
    logger.debug('------------------------ Correct command done')

    # now arrange for follower to blow up.
    ts_3.operations.explode = True

    #
    # Can't use normal command for this because it waits
    # until all followers have applied the command
    # message, assuring that the command is done. But in
    # this case one follower will not respond
    await cluster.start_auto_comms()
    command_result = None
    async def command_runner(ts):
        nonlocal command_result
        logger.debug('running command in background')
        try:
            command_result = await ts.hull.run_command("add 1", timeout=0.01)
            logger.debug('running command in background done with NO error')
        except Exception as e:
            logger.debug('running command in background error %s', traceback.format_exc())
            command_result = e
            logger.debug('running command in background done with error')
    logger.debug('------------------------ Running command ---')
    asyncio.create_task(command_runner(ts_1))
    await cluster.start_auto_comms()
    start_time = time.time()
    while time.time() - start_time < 0.25 and command_result is None:
        await asyncio.sleep(0.0001)
    assert command_result is not None
    assert command_result.result == 2
    assert ts_1.operations.total == 2

    # now we need to trigger a heartbeat so that
    # followers will see the commitIndex is higher
    # and apply and locally commit
    await ts_1.hull.state.send_heartbeats()
    
    # followers need time to run commands
    start_time = time.time()
    while time.time() - start_time < 0.25 and ts_2.operations.total != 2:
        await asyncio.sleep(0.0001)
    assert ts_2.operations.total == 2
    assert ts_3.operations.total == 1


async def test_leader_explodes_in_command(cluster_maker):
    cluster = cluster_maker(3)
    cluster.set_configs()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]
    logger = logging.getLogger(__name__)
    await cluster.start()
    await ts_1.hull.start_campaign()

    await cluster.run_election()
    assert ts_1.hull.get_state_code() == "LEADER"
    assert ts_1.hull.state.leader_uri == uri_1
    assert ts_2.hull.state.leader_uri == uri_1
    logger.info('------------------------ Election done')
    await cluster.start_auto_comms()

    command_result = await cluster.run_command("add 1", 1)
    
    assert ts_1.operations.total == 1
    assert ts_2.operations.total == 1
    assert ts_3.operations.total == 1
    logger.debug('------------------------ Correct command done')

    # now arrange for leader to blow up.
    ts_1.operations.explode = True

    command_result = await cluster.run_command("add 1", timeout=0.01)
    assert command_result is not None
    assert command_result.error is not None
    await cluster.stop_auto_comms()
    
async def test_long_catchup(cluster_maker):
    cluster = cluster_maker(3)
    cluster.set_configs()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]
    logger = logging.getLogger(__name__)
    await cluster.start()
    await ts_1.hull.start_campaign()
    await cluster.run_election()
    
    assert ts_1.hull.get_state_code() == "LEADER"
    assert ts_2.hull.state.leader_uri == uri_1
    assert ts_3.hull.state.leader_uri == uri_1
    logger.info('------------------------ Election done')
    logger.info('---------!!!!!!! starting comms')
    await cluster.start_auto_comms()

    command_result = await cluster.run_command("add 1", 1)
    assert ts_2.operations.total == 1
    assert ts_3.operations.total == 1
    logger.debug('------------------------ Correct command done')

    # Now we want to block all messages from the leader to
    # one follower, as though it has crashed, then
    # run a bunch of commands and make sure that
    # the catchup process gets them all. 
    

    logger.info('---------!!!!!!! stopping comms')
    await cluster.stop_auto_comms()
    part1 = {uri_3: ts_3}
    part2 = {uri_1: ts_1,
             uri_2: ts_2}
    logger.info('---------!!!!!!! spliting network ')
    cluster.split_network([part1, part2])
    logger.info('------------------ follower %s isolated, starting command loop', uri_3)
    await cluster.stop_auto_comms()
    # quiet the logging down
    global log_config
    old_levels = dict()

    trim_loggers = True
    if trim_loggers:
        for logger_name, spec in log_config['loggers'].items():
            logger = logging.getLogger(logger_name)
            if  logger_name == "test_commands_1" or logger_name == "Leader" or logger_name == "Follower":
                continue
            old_levels[logger_name] = logger.level
            logger.setLevel('ERROR')

    loop_limit = 50
    for i in range(loop_limit):
        command_result = await cluster.run_command("add 1", 1)
    total = ts_1.operations.total
    assert ts_2.operations.total == total
    assert ts_3.operations.total != total
    await cluster.stop_auto_comms()
    # restore the loggers
    if trim_loggers:
        for logger_name in old_levels:
            logger = logging.getLogger(logger_name)
            old_value = old_levels[logger_name]
            logger.setLevel(old_value)
    # will discard the messages that were blocked
    logger.debug('------------------ unblocking follower %s should catch up to total %d', uri_3, total)
    await cluster.deliver_all_pending()
    cluster.unsplit()
    logger.info('---------!!!!!!! starting comms')
    await cluster.start_auto_comms()
    await ts_1.hull.state.send_heartbeats()

    start_time = time.time()
    while time.time() - start_time < 0.5 and ts_3.operations.total < total:
        await asyncio.sleep(0.0001)
    assert ts_3.operations.total == total
    await cluster.stop_auto_comms()
    logger.info('------------------------ All caught up')

async def test_full_catchup(cluster_maker):
    cluster = cluster_maker(3)
    cluster.set_configs()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]
    logger = logging.getLogger(__name__)
    await cluster.start()
    await ts_1.hull.start_campaign()
    
    await cluster.run_election()
    
    assert ts_1.hull.get_state_code() == "LEADER"
    assert ts_2.hull.state.leader_uri == uri_1
    assert ts_3.hull.state.leader_uri == uri_1
    logger.info('------------------------ Election done')

    # Now we want to block all messages from the leader to
    # one follower, as though it has crashed, then
    # run a bunch of commands and make sure that
    # the catchup process gets them all. 

    logger.info('---------!!!!!!! stopping comms')
    ts_3.block_network()
    logger.info('------------------ follower %s isolated, starting command loop', uri_3)
    command_result = await cluster.run_command("add 1", 1)
    assert ts_1.operations.total == 1
    assert ts_2.operations.total == ts_1.operations.total
    logger.debug('------------------------ Correct command 1 done')
    command_result = await cluster.run_command("add 1", 1)
    assert ts_1.operations.total == 2
    assert ts_2.operations.total == ts_1.operations.total
    logger.debug('------------------------ Correct command 2 done')

    assert ts_3.operations.total != ts_1.operations.total
    # will discard the messages that were blocked
    ts_3.unblock_network()
    logger.info('------------------ unblocking follower %s should catch up to total %d', uri_3, ts_1.operations.total)
    logger.info('---------!!!!!!! starting comms')
    await cluster.start_auto_comms()
    await ts_1.hull.state.send_heartbeats()
    start_time = time.time()
    while time.time() - start_time < 0.5 and ts_3.operations.total < ts_1.operations.total:
        await asyncio.sleep(0.0001)
    assert ts_3.operations.total == ts_1.operations.total
    logger.info('------------------------ All caught up')

async def test_follower_run_error(cluster_maker):
    cluster = cluster_maker(3)
    cluster.set_configs()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]
    logger = logging.getLogger(__name__)
    await cluster.start()
    await ts_1.hull.start_campaign()
    await cluster.run_election()
    assert ts_1.hull.get_state_code() == "LEADER"
    assert ts_2.hull.state.leader_uri == uri_1
    assert ts_3.hull.state.leader_uri == uri_1
    logger.info('------------------------ Election done')

    # Block messages to one follower, run a comand,
    # then unblock it and send heartbeats, causing
    # it to try to catch up, however have the
    # "state machine" command pretend it had
    # an error. This should excersize some
    # error handling code, but then the next command
    # should go through without problem.

    logger.info('---------!!!!!!! stopping comms')
    logger.info('---------!!!!!!! spliting network ')
    ts_3.block_network()
    logger.info('------------------ follower %s isolated, running', uri_3)
    
    command_result = await cluster.run_command("add 1", 1)
    assert ts_1.operations.total == 1
    assert ts_2.operations.total == ts_1.operations.total
    logger.debug('------------------------ Correct command 1 done')

    logger.info('------------------ unblocking follower %s to hit error running command', uri_3)
    ts_3.operations.return_error = True
    ts_3.unblock_network()
    logger.info('---------!!!!!!! starting comms')
    await cluster.start_auto_comms()
    await ts_1.hull.state.send_heartbeats()
    start_time = time.time()
    while time.time() - start_time < 0.5 and not ts_3.operations.reported_error:
        await asyncio.sleep(0.0001)
    assert ts_3.operations.reported_error
    logger.info('------------------------ Error as expected, removing error insertion and trying again')
    ts_3.operations.return_error = False
    await cluster.start_auto_comms()
    await ts_1.hull.state.send_heartbeats()
    start_time = time.time()
    while time.time() - start_time < 0.5 and ts_3.operations.total !=ts_1.operations.total:
        await asyncio.sleep(0.0001)
    assert ts_3.operations.total == ts_1.operations.total


async def test_follower_rewrite_1(cluster_maker):
    await follower_rewrite12_inner(cluster_maker, True)

async def test_follower_rewrite_2(cluster_maker):
    await follower_rewrite12_inner(cluster_maker, False)
    
async def follower_rewrite12_inner(cluster_maker, command_first):
    """ Tests scenarios where a server becomes leader,
    then gets disconnected from followers, but not yet realizing
    that it accepts some client command requests, logs them, sends
    broadcast to try to commit them. The while this is going on,
    the followers hold an election and a new leader is chosen. That
    leader accepts some commands and is able to commit them because
    it has a quorum, 2 servers, in this case, itself and one follower. 
    Then the old leader connect to the new leader, and messages 
    fly to the effect that the ex-leader has log records that 
    match the index of the new leader, but not their term, so those
    records have to be discarded. After that is done the ex-leader
    can now catchup, with the help of messages from the new leader.
    Sheesh.
    """
    cluster = cluster_maker(3)
    cluster.set_configs()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]
    logger = logging.getLogger(__name__)
    await cluster.start()
    await ts_1.hull.start_campaign()
    await cluster.run_election()
    assert ts_1.hull.get_state_code() == "LEADER"
    assert ts_2.hull.state.leader_uri == uri_1
    assert ts_3.hull.state.leader_uri == uri_1
    logger.info('------------------------ Election done')
    await cluster.start_auto_comms()
    running_total = 0
    if command_first:
        command_result = await cluster.run_command("add 1", 1)
        running_total += 1
        assert ts_1.operations.total == ts_2.operations.total == ts_3.operations.total == 1
        
    last_index = await ts_1.log.get_last_index()
    logger.info("---------!!!!!!! Blocking leader's network ")
    ts_1.block_network()
    logger.info('---------!!!!!!! Sending blocked leader two "sub 1" commands')
    command_result = await ts_1.hull.run_command("sub 1", timeout=0.01)
    assert command_result.timeout_expired
    command_result = await ts_1.hull.run_command("sub 1", timeout=0.01)
    assert command_result.timeout_expired
    assert await ts_1.hull.log.get_last_index() == last_index + 2
    logger.debug('------------------------ Starting an election, favoring %s ---', uri_2)
    # now let the others do a new election
    #await ts_2.hull.log.set_term(2)
    await ts_2.hull.start_campaign()
    await cluster.run_election()
    assert ts_2.hull.get_state_code() == "LEADER"
    logger.debug('------------------------ Elected %s, demoting ex-leader %s ---', uri_2, uri_1)
    # we do this now so that the cluster run_command method will not get confused
    # about which server is the leader
    await ts_1.hull.demote_and_handle(None)
    assert ts_1.hull.get_state_code() == "FOLLOWER"

    # now do a three commands at new leader
    command_result = None
    logger.debug('------------------------ Running commands at new leader---')
    command_result = await cluster.run_command("add 1", timeout=0.01)
    running_total += 1
    assert command_result.result == running_total

    command_result = await cluster.run_command("add 1", timeout=0.01)
    running_total += 1
    assert command_result.result == running_total

    command_result = await cluster.run_command("add 1", timeout=0.01)
    running_total += 1
    assert command_result.result == running_total
    
    total = ts_2.operations.total
    # ts_3 needs a heartbeat to know to commit
    await ts_2.hull.state.send_heartbeats()
    start_time = time.time()
    while time.time() - start_time < 0.25 and ts_3.operations.total != running_total:
        await cluster.deliver_all_pending()
        await asyncio.sleep(0.0001)
    assert ts_3.operations.total == total

    # Now let the ex-leader rejoin, already demoted to
    # follower, and let it get a heartbeat. this should trigger it to
    # overwrite the existing records in its log with the new ones
    # from the new leader.
    #
    # The ex-leadere will have two or four records in the log, depending
    # on whether this function was run with "command_firsT" True.
    # In either case, the first record will be the "no-op" or "TERM_START"
    # record for when the ex-leader took power.
    # If command_first was False, then there will ony be two command records in the
    # log, for the two "sub 1" commands. 
    # If command_first was True, then there will ony be one "add 1" record in the
    # log that should also be present in the logs of the other two servers, since the
    # command was committed before the break. Then there should two command records 
    # logged for the two "sub 1" commands.
    #
    # Capture the content of the two "sub 1" records, which will be overwritten
    # when the cluster heals and the ex-leader synchronizes.
    if command_first:
        first_relevant_index = 3
    else:
        first_relevant_index = 2
    orig_1 = await ts_1.hull.log.read(first_relevant_index) # the first record is start term record
    orig_2 = await ts_1.hull.log.read(first_relevant_index + 1)
    logger.debug('------------------------ Unblocking ex-leader, should overwrite logs ---')
    ts_1.unblock_network() # discards missed messages
    await ts_2.hull.state.send_heartbeats()
    await cluster.deliver_all_pending()
    start_time = time.time()
    # log should be 1 for start_term, and one for each command, so 4
    while time.time() - start_time < 0.5 and await ts_1.log.get_last_index() != await ts_2.log.get_last_index():
        await asyncio.sleep(0.0001)

    assert await ts_1.log.get_last_index() == await ts_2.log.get_last_index()
    new_1 = await ts_1.log.read(first_relevant_index) # the first record is start term record
    new_2 = await ts_1.log.read(first_relevant_index + 1)
    assert new_1.command != orig_1.command
    assert new_2.command != orig_2.command


