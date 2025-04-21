#!/usr/bin/env python
import asyncio
import logging
import pytest
import time
from raftengine.messages.request_vote import RequestVoteMessage,RequestVoteResponseMessage
from raftengine.messages.append_entries import AppendEntriesMessage, AppendResponseMessage
from servers import setup_logging

extra_logging = [dict(name=__name__, level="debug"),]
setup_logging(extra_logging)

from servers import WhenElectionDone
from servers import PausingCluster, cluster_maker

async def test_partition_1(cluster_maker):
    cluster = cluster_maker(5)
    cluster.set_configs()
    uri_1 = cluster.node_uris[0]
    uri_2 = cluster.node_uris[1]
    uri_3 = cluster.node_uris[2]
    uri_4 = cluster.node_uris[3]
    uri_5 = cluster.node_uris[4]

    ts_1 = cluster.nodes[uri_1]
    ts_2 = cluster.nodes[uri_2]
    ts_3 = cluster.nodes[uri_3]
    ts_4 = cluster.nodes[uri_4]
    ts_5 = cluster.nodes[uri_5]

    logger = logging.getLogger(__name__)
    await cluster.start()
    await ts_1.hull.start_campaign()
    ts_1.set_trigger(WhenElectionDone())
    ts_2.set_trigger(WhenElectionDone())
    ts_3.set_trigger(WhenElectionDone())
    ts_4.set_trigger(WhenElectionDone())
    ts_5.set_trigger(WhenElectionDone())
        
    await asyncio.gather(ts_1.run_till_triggers(),
                         ts_2.run_till_triggers(),
                         ts_3.run_till_triggers(),
                         ts_4.run_till_triggers(),
                         ts_5.run_till_triggers())
    
    ts_1.clear_triggers()
    ts_2.clear_triggers()
    ts_3.clear_triggers()
    ts_4.clear_triggers()
    ts_5.clear_triggers()
    assert ts_1.hull.get_state_code() == "LEADER"
    assert ts_2.hull.state.leader_uri == uri_1
    assert ts_3.hull.state.leader_uri == uri_1
    assert ts_4.hull.state.leader_uri == uri_1
    assert ts_5.hull.state.leader_uri == uri_1

    logger.info('-------- Election done, saving a command record')
    await cluster.start_auto_comms()
    command_result = await ts_1.hull.apply_command("add 1")
    assert command_result is not None
    assert command_result.result is not None
    assert ts_1.operations.total == 1
    assert ts_2.operations.total == 1
    assert ts_3.operations.total == 1
    assert ts_4.operations.total == 1
    assert ts_5.operations.total == 1

    logger.info('--------- Everbody has first record, partitioning network')

    part1 = {uri_1: ts_1,
             uri_2: ts_2,
             uri_3: ts_3}
    part2 = {uri_4: ts_4,
             uri_5: ts_5}
    cluster.net_mgr.split_network([part1, part2])
    
    logger.info('--------- Everbody has first record, partition done, repleating command')
    command_result = await ts_1.hull.apply_command("add 1")
    assert command_result is not None
    assert command_result.result is not None
    assert ts_1.operations.total == 2
    assert ts_2.operations.total == 2
    assert ts_3.operations.total == 2
    assert ts_4.operations.total == 1
    assert ts_5.operations.total == 1
    logger.info('--------- Main partition has update, doing it again')
    command_result = await ts_1.hull.apply_command("add 1")
    assert command_result is not None
    assert command_result.result is not None
    assert ts_1.operations.total == 3
    assert ts_2.operations.total == 3
    assert ts_3.operations.total == 3
    assert ts_4.operations.total == 1
    assert ts_5.operations.total == 1

    logger.info('--------- Now healing partition and looking for sync ----')
    await cluster.stop_auto_comms()
    cluster.net_mgr.unsplit()
    ts_1.hull.state.last_broadcast_time = 0
    await ts_1.hull.state.send_heartbeats()
    # gonna send four
    assert await ts_1.do_next_out_msg()  is not None
    assert await ts_1.do_next_out_msg()  is not None
    assert await ts_1.do_next_out_msg()  is not None
    last_out = await ts_1.do_next_out_msg()
    assert last_out is not None

    # let the up to date node do their sequence
    assert await ts_2.do_next_in_msg() is not None
    assert await ts_2.do_next_out_msg() is not None
    assert await ts_3.do_next_in_msg() is not None
    assert await ts_3.do_next_out_msg() is not None
    # get two back, now those guys are out of the way
    assert await ts_1.do_next_in_msg() is not None
    assert await ts_1.do_next_in_msg() is not None

    # so know we can let are behind the times ones respond

    logger.debug('--------- 4 and 5 should be pending, doing full sequence on one then other ')
    for node in [ts_4, ts_5]:
        assert await node.do_next_in_msg() is not None
        assert await node.do_next_out_msg() is not None

        # now we should ping pong till good
        # leader gets the news
        assert await ts_1.do_next_in_msg() is not None
        # respond with log record
        assert await ts_1.do_next_out_msg() is not None
        # processing it
        assert await node.do_next_in_msg() is not None
        assert node.operations.total == 2
        # THANK YOU SIR, MAY I HAVE ANOTHER!!!!???
        assert await node.do_next_out_msg() is not None
        # leader considers
        assert await ts_1.do_next_in_msg() is not None
        # leader response
        assert await ts_1.do_next_out_msg() is not None
        # processing it
        assert await node.do_next_in_msg() is not None
        assert node.operations.total == 3
        # Life is good
    
    if False:
        command_result = await ts_1.hull.apply_command("add 1")
        assert command_result is not None
        assert command_result.result is not None
        assert ts_1.operations.total == 4
        assert ts_2.operations.total == 4
        assert ts_3.operations.total == 4
