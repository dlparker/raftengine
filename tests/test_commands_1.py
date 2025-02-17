#!/usr/bin/env python
import asyncio
import logging
import pytest
import time
import traceback
from raftengine.messages.request_vote import RequestVoteMessage,RequestVoteResponseMessage
from raftengine.messages.append_entries import AppendEntriesMessage, AppendResponseMessage
from raftengine.log.log_api import LogRec

from servers import WhenMessageOut, WhenMessageIn
from servers import WhenHasLogIndex
from servers import WhenInMessageCount, WhenElectionDone
from servers import WhenAllMessagesForwarded, WhenAllInMessagesHandled
from servers import PausingCluster, cluster_maker
from servers import SNormalElection
from servers import setup_logging

extra_logging = [dict(name=__name__, level="debug"), dict(name="Triggers", level="debug")]
setup_logging(extra_logging)

async def test_command_1(cluster_maker):
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

    command_result = await ts_3.hull.apply_command("add 1")
    assert command_result.result is not None
    assert command_result.error is None
    assert ts_1.operations.total == 1
    assert ts_2.operations.total == 1
    assert ts_3.operations.total == 1
    term = await ts_3.hull.log.get_term()
    index = await ts_3.hull.log.get_last_index()
    assert index == 1
    assert await ts_1.hull.log.get_term() == term
    assert await ts_1.hull.log.get_last_index() == index
    assert await ts_2.hull.log.get_term() == term
    assert await ts_2.hull.log.get_last_index() == index
    logger.debug('------------------------ Correct command done')
    
    await cluster.stop_auto_comms()
    command_result = await ts_1.hull.apply_command("add 1")
    assert command_result.redirect == uri_3
    logger.debug('------------------------ Correct redirect (follower) done')
    
    orig_term =  await ts_1.hull.get_term() 
    await ts_1.hull.state.leader_lost()
    assert ts_1.hull.get_state_code() == "CANDIDATE"
    command_result = await ts_1.hull.apply_command("add 1")
    assert command_result.retry is not None
    logger.debug('------------------------ Correct retry (candidate) done')
    # cleanup attempt to start election
    ts_1.clear_all_msgs()
    # set term back so it won't trigger leader to quit
    await ts_1.hull.get_log().set_term(orig_term)

    await ts_1.hull.demote_and_handle()
    await ts_3.hull.state.send_heartbeats()
    await cluster.deliver_all_pending()
    assert ts_1.hull.get_state_code() == "FOLLOWER"

    # Have a follower blow up, control the messages so that
    # leader only sends two append_entries, then check
    # for bad state on exploded follower. Then defuse
    # the exploder and trigger hearbeat. This should
    # result in replay of command to follower, which should
    # then catch up and the the correct state

    command_result = None
    async def command_runner(ts):
        nonlocal command_result
        logger.debug('running command in background')
        try:
            command_result = await ts.hull.apply_command("add 1")
        except Exception as e:
            logger.debug('running command in background error %s', traceback.format_exc())
            
        logger.debug('running command in background done')
    
    ts_1.operations.explode = True
    orig_index = await ts_3.hull.get_log().get_last_index()
    ts_3.set_trigger(WhenHasLogIndex(orig_index + 1))
    # also have to fiddle the heartbeat timer or the messages won't be sent
    loop = asyncio.get_event_loop()
    logger.debug('------------------------ Starting command runner ---')
    loop.create_task(command_runner(ts_3))
    logger.debug('------------------------ Starting run_till_triggers with others ---')
    await ts_3.run_till_triggers(free_others=True)
    ts_3.clear_triggers()
    assert command_result is not None
    assert command_result.result is not None
    assert command_result.error is None
    assert ts_1.operations.exploded == True

    assert ts_2.operations.total == 2
    assert ts_3.operations.total == 2
    assert ts_1.operations.total == 1

    # do it a couple more times so we can test that catch up function works
    # when follower is behind more than one record
    
    orig_index = await ts_3.hull.get_log().get_last_index()
    ts_3.set_trigger(WhenHasLogIndex(orig_index + 1))
    # also have to fiddle the heartbeat timer or the messages won't be sent
    loop = asyncio.get_event_loop()
    logger.debug('------------------------ Starting command runner ---')
    loop.create_task(command_runner(ts_3))
    logger.debug('------------------------ Starting run_till_triggers with others ---')
    await ts_3.run_till_triggers(free_others=True)
    ts_3.clear_triggers()

    assert ts_2.operations.total == 3
    assert ts_3.operations.total == 3
    assert ts_1.operations.total == 1

    orig_index = await ts_3.hull.get_log().get_last_index()
    ts_3.set_trigger(WhenHasLogIndex(orig_index + 1))
    # also have to fiddle the heartbeat timer or the messages won't be sent
    loop = asyncio.get_event_loop()
    logger.debug('------------------------ Starting command runner ---')
    loop.create_task(command_runner(ts_3))
    logger.debug('------------------------ Starting run_till_triggers with others ---')
    await ts_3.run_till_triggers(free_others=True)
    ts_3.clear_triggers()

    assert ts_2.operations.total == 4
    assert ts_3.operations.total == 4
    assert ts_1.operations.total == 1

    # now send heartbeats and ensure that exploded follower catches up
    ts_1.operations.explode = False
    ts_3.hull.state.last_broadcast_time = 0
    logger.debug('---------Sending heartbeat and starting run_till_triggers with others ---')
    await ts_3.hull.state.send_heartbeats()
    cur_index = await ts_3.hull.get_log().get_last_index()
    ts_1.set_trigger(WhenHasLogIndex(2))
    await ts_1.run_till_triggers(free_others=True)
    
    try:
        ts_1.set_trigger(WhenHasLogIndex(3))
        await ts_1.run_till_triggers(free_others=True)
        ts_1.set_trigger(WhenHasLogIndex(4))
        await ts_1.run_till_triggers(free_others=True)
    except:
        print(await ts_1.log.get_last_index())
        print(await ts_1.log.get_last_index())
        breakpoint()
        print(await ts_1.log.get_last_index())
        print(await ts_1.log.get_last_index())
    
    assert ts_1.operations.total == 4

async def test_command_sqlite_1(cluster_maker):
    from dev_tools.sqlite_log import SqliteLog
    cluster = cluster_maker(3, use_log=SqliteLog)
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

    command_result = await ts_3.hull.apply_command("add 1")
    assert command_result.result is not None
    assert command_result.error is None
    assert ts_1.operations.total == 1
    assert ts_2.operations.total == 1
    assert ts_3.operations.total == 1
    term = await ts_3.hull.log.get_term()
    index = await ts_3.hull.log.get_last_index()
    assert index == 1
    assert await ts_1.hull.log.get_term() == term
    assert await ts_1.hull.log.get_last_index() == index
    assert await ts_2.hull.log.get_term() == term
    assert await ts_2.hull.log.get_last_index() == index
    logger.debug('------------------------ Correct command done')
    rec_1 = await ts_1.hull.log.read(index)
    rec_2 = await ts_2.hull.log.read(index)
    rec_3 = await ts_3.hull.log.read(index)
    assert rec_1.user_data == rec_2.user_data 
    assert rec_1.user_data == rec_3.user_data
    new_rec = LogRec.from_dict(rec_1.__dict__)
    assert new_rec.user_data == rec_1.user_data
    await cluster.stop_auto_comms()
    
async def double_leader_inner(cluster, discard):
    cluster.set_configs()
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
    logger.error('---------!!!!!!! starting comms')
    await cluster.start_auto_comms()

    command_result = await ts_1.hull.apply_command("add 1")
    assert command_result.result is not None
    assert command_result.error is None
    assert ts_1.operations.total == 1
    assert ts_2.operations.total == 1
    assert ts_3.operations.total == 1
    logger.debug('------------------------ Correct command done')

    # Now we want to block all messages from the leader, then
    # trigger a follower to hold an election, wait for it to
    # win, then unblock the old leader, and then try another
    # command. The leader should figure out it doesn't lead
    # anymore and give back a redirect

    logger.error('---------!!!!!!! stopping comms')
    await cluster.stop_auto_comms()
    ts_1.block_network()
    logger.info('------------------ isolated leader, starting new election')
    await ts_2.hull.start_campaign()
    sequence = SNormalElection(cluster, 1)
    await cluster.run_sequence(sequence)
    assert ts_1.hull.get_state_code() == "LEADER"
    assert ts_2.hull.get_state_code() == "LEADER"
    assert ts_3.hull.state.leader_uri == uri_2

    if discard:
        # will discard the messages that were blocked so
        # leader gets missed messages
        ts_1.unblock_network()
        logger.error('---------!!!!!!! starting comms')
        await cluster.start_auto_comms()
    else:
        # will deliver blocked message
        ts_1.unblock_network(deliver=True)
        await cluster.start_auto_comms()
        
    logger.debug('------------------ Command AppendEntries should get rejected -')
    command_result = await ts_1.hull.apply_command("add 1", timeout=1)
    assert command_result.redirect == uri_2
    logger.error('---------!!!!!!! stopping comms')
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
    sequence = SNormalElection(cluster, 1)
    await cluster.run_sequence(sequence)
    
    assert ts_1.hull.get_state_code() == "LEADER"
    assert ts_2.hull.state.leader_uri == uri_1
    assert ts_3.hull.state.leader_uri == uri_1
    logger = logging.getLogger(__name__)
    logger.info('-------------- Election done, about to split network leaving leader %s isolated ', uri_1)
    await cluster.start_auto_comms()

    command_result = await ts_1.hull.apply_command("add 1")
    assert command_result.result is not None
    assert command_result.error is None
    assert ts_1.operations.total == 1
    assert ts_2.operations.total == 1
    assert ts_3.operations.total == 1

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
    ts_2.set_trigger(WhenElectionDone(voters=[uri_2, uri_3]))
    ts_3.set_trigger(WhenElectionDone(voters=[uri_2, uri_3]))
    
    await asyncio.gather(ts_2.run_till_triggers(),
                         ts_3.run_till_triggers())
    
    ts_2.clear_triggers()
    ts_3.clear_triggers()

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
    ts_1.hull.state.last_broadcast_time = 0
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
    
    
    
