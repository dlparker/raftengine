#!/usr/bin/env python
import asyncio
import logging
import time
import json
from pathlib import Path
import pytest
from raftengine.messages.append_entries import AppendEntriesMessage
from raftengine.messages.message_codec import MessageCodec

from dev_tools.sequences import SNormalElection
from dev_tools.pausing_cluster import cluster_maker
from dev_tools.log_control import setup_logging
from dev_tools.features import FeatureRegistry

# Initialize feature registry
registry = FeatureRegistry.get_registry()

log_control = setup_logging()
logger = logging.getLogger("test_code")

async def test_slow_voter(cluster_maker):
    """
    This tests the rare case where a candidate starts a new election, sends requests, then for some
    reason starts another election at a higher term and then receives a vote reponse from the previous term.
    This seems pretty unlikely in practice, but not impossible, so there is code for it. About three lines.
    All this test does is poke those lines.

    It goes like this:

    1. Normal election
    2. The leader (node 3) is forced to start a new election.
    3. Messages are managed such that the followers get the requests for vote and send replies,
       but everything stops before the candidate gets their responses.
    4. The candidate starts a new election, so term is now 3
    5. The messages are processed enough to see that the candidate gets the stale once, and
       then the new voting cycle works and yes votes for the new term arrive.
    6. The rest of the messages are delivered to complete the election

    The test is run with pre_vote disabled. The relavant part is when the actual votes happen,
    and the test would be much more complicated if we had to handle pre vote messages too.
    
    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """
    
    # Feature definitions - stale vote handling and election edge cases
    f_stale_vote_handling = registry.get_raft_feature("leader_election", "stale_vote_handling")
    f_term_advancement = registry.get_raft_feature("leader_election", "term_advancement")
    f_election_timeout_retry = registry.get_raft_feature("leader_election", "election_timeout_retry")
    f_automated_election = registry.get_raft_feature("leader_election", "automated_election_process")
    f_test_sequencing = registry.get_raft_feature("test_infrastructure", "test_sequencing")
    f_role_transitions = registry.get_raft_feature("leader_election", "role_transitions")
    
    cluster = cluster_maker(3)
    config = cluster.build_cluster_config(use_pre_vote=False)
    cluster.set_configs(config)
    uri_1 = cluster.node_uris[0]
    uri_2 = cluster.node_uris[1]
    uri_3 = cluster.node_uris[2]

    ts_1 = cluster.nodes[uri_1]
    ts_2 = cluster.nodes[uri_2]
    ts_3 = cluster.nodes[uri_3]

    await cluster.test_trace.define_test("Testing slow voter scenario in election", logger=logger)
    
    # Section 1: Initial election establishment
    spec = dict(used=[f_automated_election], tested=[])
    await cluster.test_trace.start_test_prep("Normal election", features=spec)
    await cluster.start()
    await ts_3.start_campaign()
    sequence = SNormalElection(cluster, 1)
    await cluster.run_sequence(sequence)
    
    assert ts_3.get_role_name() == "LEADER"
    assert ts_1.get_leader_uri() == uri_3
    assert ts_2.get_leader_uri() == uri_3

    # Now get an re-election started on current leader,
    # but block the follower's votes, then trigger the
    # candidate to retry, which will up the term, then let
    # the old votes flow in. They should get ignored
    # and the election should succeed
    # Section 2: First election setup with stale vote creation
    spec = dict(used=[f_test_sequencing, f_role_transitions], tested=[])
    await cluster.test_trace.start_subtest("Node 3 is leader, demoting and ensuring vote requests are delivered, but responses not accepted yet", features=spec)
    await ts_3.do_demote_and_handle(None)
    await ts_3.do_leader_lost()
    await ts_3.do_next_out_msg()
    await ts_3.do_next_out_msg()
    msg = await ts_1.do_next_in_msg()
    assert msg is not None
    msg = await ts_2.do_next_in_msg()
    assert msg is not None
    assert len(ts_1.out_messages) == 1
    assert len(ts_2.out_messages) == 1
    old_term = await ts_3.log.get_term()
    # Section 3: Second election with stale vote detection
    spec = dict(used=[f_term_advancement], tested=[f_stale_vote_handling])
    await cluster.test_trace.start_subtest("Starting another election at node 3, whose term is now 3 and checking that pending messages are stale", features=spec)
    await ts_3.start_campaign()
    assert old_term + 1 == await ts_3.log.get_term()
    # this should be a stale vote
    msg = await ts_1.do_next_out_msg()
    msg = await ts_3.do_next_in_msg()
    assert msg.term == old_term
    # this too
    msg = await ts_2.do_next_out_msg()
    msg = await ts_3.do_next_in_msg()
    assert msg.term == old_term
    logger.debug("--------------------Stale votes processed")
    # stale votes should be ignored, election should complete normally

    # so we need two more outs from the candidate ts_3
    # two more ins for the followers
    # then two outs from them to get their new votes
    # then two ins to candiate and the first one should
    # settle the election
    # Section 4: Election completion with correct term handling
    spec = dict(used=[f_test_sequencing], tested=[f_election_timeout_retry])
    await cluster.test_trace.start_subtest("Allowing some messages for second election, checking that term is correct", features=spec)
    new_term = await ts_3.log.get_term()
    await ts_3.do_next_out_msg()
    await ts_3.do_next_out_msg()
    await ts_2.do_next_in_msg()
    msg = await ts_2.do_next_out_msg()
    assert msg.term == new_term
    assert msg.vote == True
    await ts_1.do_next_in_msg()
    msg = await ts_1.do_next_out_msg()
    assert msg.term == new_term
    assert msg.vote == True
    # Section 5: Final election completion
    spec = dict(used=[f_automated_election], tested=[])
    await cluster.test_trace.start_subtest("Allowing remainging messages for normal election to complete", features=spec)
    await cluster.deliver_all_pending()
    assert ts_3.get_role_name() == "LEADER"
    assert ts_1.get_leader_uri() == uri_3
    assert ts_2.get_leader_uri() == uri_3

async def test_message_errors(cluster_maker):
    """
    This test uses error insertion to make things that normally don't blow up do so. Code that
    gets run a million times with no problem, but that has the potential to blow up if something
    funky like memory corruption happens. We have code to catch these cases, so there needs
    to be code to test that the catches work.

    Starts with a normal election, then inserts two errors into the message processing code.
    
    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """
    
    # Feature definitions - message error handling and corruption testing
    f_error_injection = registry.get_raft_feature("test_infrastructure", "error_injection")
    f_message_error_handling = registry.get_raft_feature("system_reliability", "message_error_handling")
    f_automated_election = registry.get_raft_feature("leader_election", "automated_election_process")
    f_test_sequencing = registry.get_raft_feature("test_infrastructure", "test_sequencing")
    f_heartbeat_processing = registry.get_raft_feature("log_replication", "heartbeat_processing")
    f_message_corruption = registry.get_raft_feature("system_reliability", "message_corruption_handling")
    
    cluster = cluster_maker(3)
    config = cluster.build_cluster_config()
    cluster.set_configs(config)
    uri_1 = cluster.node_uris[0]
    uri_2 = cluster.node_uris[1]
    uri_3 = cluster.node_uris[2]

    ts_1 = cluster.nodes[uri_1]
    ts_2 = cluster.nodes[uri_2]
    ts_3 = cluster.nodes[uri_3]

    await cluster.test_trace.define_test("Testing message processing errors", logger=logger)
    
    # Section 1: Initial election establishment
    spec = dict(used=[f_test_sequencing], tested=[])
    await cluster.test_trace.start_test_prep("Normal election", features=spec)
    await cluster.start()
    await ts_3.start_campaign()
    sequence = SNormalElection(cluster, 1)
    await cluster.run_sequence(sequence)
    assert ts_3.get_role_name() == "LEADER"
    assert ts_1.get_leader_uri() == uri_3
    assert ts_2.get_leader_uri() == uri_3
    
    # Section 2: Message explosion error injection and handling
    spec = dict(used=[f_error_injection, f_heartbeat_processing], tested=[f_message_error_handling])
    await cluster.test_trace.start_subtest("Injecting message explosion errors during heartbeat processing", features=spec)
    
    ts_1.deck.explode_on_message_code = AppendEntriesMessage.get_code()
    
    hist = ts_1.get_message_problem_history(clear=True)
    await ts_3.send_heartbeats()
    await ts_3.do_next_out_msg()
    await ts_3.do_next_out_msg()
    await ts_1.do_next_in_msg()
    
    hist = ts_1.get_message_problem_history(clear=True)
    assert len(hist) == 1
    
    ts_1.deck.explode_on_message_code = None

    # Section 3: Message corruption error injection and handling
    spec = dict(used=[f_error_injection, f_heartbeat_processing], tested=[f_message_corruption])
    await cluster.test_trace.start_subtest("Injecting message corruption errors during heartbeat processing", features=spec)

    ts_1.deck.corrupt_message_with_code = AppendEntriesMessage.get_code()
    await ts_3.send_heartbeats()
    await ts_3.do_next_out_msg()
    await ts_3.do_next_out_msg()
    await ts_1.do_next_in_msg()
    hist = ts_1.get_message_problem_history(clear=True)
    assert len(hist) == 1

async def test_message_serializer(cluster_maker):
    """
    There is code in the deck inner_on_message method which is called by
    the on_message method that serializes message handling to FIFO order.
    In the words of the Project Farm youtube channel, we're gonna test that!
    """
    
    # Feature definitions - message serialization and processing order
    f_message_serialization = registry.get_raft_feature("system_reliability", "message_serialization")
    f_automated_election = registry.get_raft_feature("leader_election", "automated_election_process")
    f_test_sequencing = registry.get_raft_feature("test_infrastructure", "test_sequencing")
    f_command_execution = registry.get_raft_feature("log_replication", "command_execution")
    f_message_interceptors = registry.get_raft_feature("test_infrastructure", "message_interceptors")
    f_serializer_timeout = registry.get_raft_feature("system_reliability", "serializer_timeout_handling")
    
    cluster = cluster_maker(3)
    config = cluster.build_cluster_config()
    cluster.set_configs(config)
    uri_1 = cluster.node_uris[0]
    uri_2 = cluster.node_uris[1]
    uri_3 = cluster.node_uris[2]

    ts_1 = cluster.nodes[uri_1]
    ts_2 = cluster.nodes[uri_2]
    ts_3 = cluster.nodes[uri_3]

    await cluster.test_trace.define_test("Testing message serialization and FIFO ordering", logger=logger)
    
    # Section 1: Initial election establishment
    spec = dict(used=[f_automated_election, f_test_sequencing], tested=[])
    await cluster.test_trace.start_test_prep("Normal election", features=spec)
    await cluster.start()
    await ts_1.start_campaign()
    sequence = SNormalElection(cluster, 1)
    await cluster.run_sequence(sequence)
    assert ts_1.get_role_name() == "LEADER"
    assert ts_2.get_leader_uri() == uri_1
    assert ts_3.get_leader_uri() == uri_1

    # Section 2: Message serialization with interceptor testing
    spec = dict(used=[f_message_interceptors, f_command_execution], tested=[f_message_serialization])
    await cluster.test_trace.start_subtest("Setting up message interceptor to test FIFO serialization during command processing", features=spec)
    
    # I need a message to get delayed in processing so that I can send another
    # message while it is pending. We'll do that by making the pausing server
    # route outgoing messages to an intercepter and having it hold up
    # execution, then forcing another message.
    # So we make all this happend by installing the interceptor in one of the
    # followers, then running two commands. When the first command
    # append_entries hits the intercepted follower, it holds, but the command
    # completes because the other follower says yes. Then the
    # second command runs, and the held follower gets the second append_entries.
    # At that point we check to see that the interceptor does not fire again,
    # and then we release the first message, then check to see that the
    # intereceptor does fire again.

    trapped_msg = None
    release_msg = asyncio.Condition()
    async def interceptor(other_node, msg, serial_number):
        nonlocal trapped_msg
        trapped_msg = msg
        try:
            async with release_msg:
                await asyncio.wait_for(release_msg.wait(), timeout=1.0)
                print('------------ Releasing intercepted message -----------------')
                return True
        except asyncio.exceptions.CancelledError:
            pass
    await ts_3.add_interceptor(interceptor, msg_op="out", msg_type="append_response")
    voters = [uri_1, uri_2]
    command_result = await cluster.run_command("add 1", timeout=2.0, voters=voters)
    async def poker():
        await ts_3.do_next_in_msg()
    asyncio.create_task(poker())
    await asyncio.sleep(0.0001)
    assert trapped_msg is not None

    command_result = await cluster.run_command("add 1", timeout=2.0, voters=voters)
    trapped_msg = None
    # intercepter should not hit because new message should
    # pend on completion of old one
    asyncio.create_task(poker())
    await asyncio.sleep(0.0001)
    assert trapped_msg is None
    async with release_msg:
        release_msg.notify_all()
    # intercepter should  hit  now 
    await asyncio.sleep(0.01)
    assert trapped_msg is not None
    async with release_msg:
        release_msg.notify_all()
    await asyncio.sleep(0.0001)

    # Section 3: Serializer timeout testing
    spec = dict(used=[f_test_sequencing], tested=[f_serializer_timeout])
    await cluster.test_trace.start_subtest("Testing message serializer timeout handling", features=spec)
    
    # now make the message serialize timeout
    command_result = await cluster.run_command("add 1", timeout=2.0, voters=voters)
    trapped_msg = None

    asyncio.create_task(poker())
    await asyncio.sleep(0.0001)
    assert trapped_msg is not None
    hist = ts_3.get_message_problem_history(clear=True)

    # now it is delaying, try to send it again directly so we can catch the
    # timeout
    emsg, serial = MessageCodec.encode_message(trapped_msg)
    delay = 0.0001
    ts_3.deck.message_serializer_timeout = delay/2
    await ts_3.deck.on_message(emsg)
    hist = ts_3.get_message_problem_history(clear=True)
    assert len(hist) == 1
    async with release_msg:
        release_msg.notify_all()
    await asyncio.sleep(0.01)

