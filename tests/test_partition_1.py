#!/usr/bin/env python
import asyncio
import logging
import pytest
import time
from raftengine.messages.request_vote import RequestVoteMessage,RequestVoteResponseMessage
from raftengine.messages.append_entries import AppendEntriesMessage, AppendResponseMessage

from dev_tools.servers import WhenElectionDone
from dev_tools.servers import PausingCluster, cluster_maker
from dev_tools.servers import SNormalElection, SNormalCommand, SPartialCommand
from dev_tools.servers import setup_logging

#extra_logging = [dict(name=__name__, level="debug"),]
#setup_logging(extra_logging)
setup_logging()
logger = logging.getLogger("test_code")

async def test_partition_1(cluster_maker):
    cluster = cluster_maker(5)
    cluster.set_configs()

    uri_1, uri_2, uri_3, uri_4, uri_5 = cluster.node_uris
    ts_1, ts_2, ts_3, ts_4, ts_5 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3, uri_4, uri_5]]

    await cluster.start()
    await ts_1.hull.start_campaign()

    sequence = SNormalElection(cluster, 1)
    await cluster.run_sequence(sequence)
    

    assert ts_1.hull.get_state_code() == "LEADER"
    assert ts_2.hull.state.leader_uri == uri_1
    assert ts_3.hull.state.leader_uri == uri_1
    assert ts_4.hull.state.leader_uri == uri_1
    assert ts_5.hull.state.leader_uri == uri_1

    logger.info('-------- Election done, saving a command record')
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


    logger.info('--------- Everbody has first record, partitioning network')

    part1 = {uri_1: ts_1,
             uri_2: ts_2,
             uri_3: ts_3}
    part2 = {uri_4: ts_4,
             uri_5: ts_5}
    cluster.split_network([part1, part2])
    
    logger.info('--------- Everbody has first record, partition done, repeating command')
    sequence3 = SNormalCommand(cluster, "add 1", 1)
    command_result = await cluster.run_sequence(sequence3)
    assert command_result is not None
    assert command_result.result is not None
    assert ts_1.operations.total == 2
    assert ts_2.operations.total == 2
    assert ts_3.operations.total == 2
    assert ts_4.operations.total == 1
    assert ts_5.operations.total == 1
    logger.info('--------- Main partition has update, doing it again')
    sequence4 = SNormalCommand(cluster, "add 1", 1)
    command_result = await cluster.run_sequence(sequence4)
    assert command_result is not None
    assert command_result.result is not None
    assert ts_1.operations.total == 3
    assert ts_2.operations.total == 3
    assert ts_3.operations.total == 3
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

    logger.info('--------- Now healing partition and looking for sync ----')
    await cluster.stop_auto_comms()
    cluster.net_mgr.unsplit()
    logger.info('--------- Sending heartbeats ----')
    await ts_1.hull.state.send_heartbeats()
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
    assert await ts_2.do_next_in_msg() is not None
    assert await ts_2.do_next_out_msg() is not None
    assert await ts_3.do_next_in_msg() is not None
    assert await ts_3.do_next_out_msg() is not None
    # get two back, now those guys are out of the way
    replys = []
    for i in range(2):
        msg = await ts_1.do_next_in_msg()
        assert msg is not None
        assert msg.sender in [uri_2, uri_3]
    # so know we can let are behind the times ones respond

    logger.debug('--------- 4 and 5 should be pending, doing message sequence on one then other ')
    for node in [ts_4, ts_5]:
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
        assert backdown1.prevLogIndex == 3
        # now have the node accept it
        assert await node.do_next_in_msg() is not None
        # and send a response, should so no match
        catchup_request2 =  await node.do_next_out_msg()
        catchup_request2 is not None
        assert catchup_request2.success == False
        assert catchup_request2.maxIndex == 2
        # let the leader collect t
        assert await ts_1.do_next_in_msg() is not None

        # this will be another backdown, this one should match
        backdown2 = await ts_1.do_next_out_msg()
        assert backdown2 is not None
        assert backdown2.commitIndex == 4
        assert backdown2.prevLogIndex == 2
        # now have the node accept it
        assert await node.do_next_in_msg() is not None
        # and send a response, should say we're good to this point
        catchup_request3 =  await node.do_next_out_msg()
        assert catchup_request3.success == True
        assert catchup_request3.maxIndex == 3
        # let the leader collect t
        assert await ts_1.do_next_in_msg() is not None

        # this will be a catchup, one record
        catchup = await ts_1.do_next_out_msg()
        assert catchup is not None
        assert catchup.commitIndex == 4
        assert catchup.prevLogIndex == 3
        # now have the node accept it
        assert await node.do_next_in_msg() is not None
        # and send a response, should say we're good to end
        catchup_result =  await node.do_next_out_msg()
        assert catchup_result.success == True
        assert catchup_result.maxIndex == 4
        # let the leader collect t
        assert await ts_1.do_next_in_msg() is not None

    # give time for applying command    
    await asyncio.sleep(0.01)


    assert ts_4.operations.total == 3
    assert ts_5.operations.total == 3

async def test_partition_2_leader(cluster_maker):
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


    part1 = {uri_1: ts_1}
    part2 = {uri_2: ts_2,
             uri_3: ts_3}
    cluster.split_network([part1, part2])

    logger.info('---------!!!!!!! stopping comms')
    await ts_2.hull.start_campaign()
    await cluster.run_election()
    assert ts_1.hull.get_state_code() == "LEADER"
    assert ts_2.hull.get_state_code() == "LEADER"
    assert ts_3.hull.state.leader_uri == uri_2
    command_result = await cluster.run_command("add 1", 1)
    assert ts_2.operations.total == 2
    cluster.unsplit()
    logger.info('------------------------ Sending heartbeats from out of date leader')
    await ts_1.hull.state.send_heartbeats()
    await cluster.deliver_all_pending()
    assert ts_1.hull.get_state_code() == "FOLLOWER"
    # let ex-leader catch up
    await ts_2.hull.state.send_heartbeats()
    await cluster.deliver_all_pending()
    assert ts_1.operations.total == 2
    logger.info('------------------------ Leadership change correctly detected')
