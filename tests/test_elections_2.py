#!/usr/bin/env python
import asyncio
import logging
import time
from pathlib import Path
import pytest
from raftengine.messages.request_vote import RequestVoteMessage,RequestVoteResponseMessage
from raftengine.messages.append_entries import AppendEntriesMessage, AppendResponseMessage


from dev_tools.servers import WhenMessageOut, WhenMessageIn
from dev_tools.servers import WhenIsLeader, WhenHasLeader
from dev_tools.servers import WhenElectionDone
from dev_tools.servers import WhenAllMessagesForwarded, WhenAllInMessagesHandled
from dev_tools.servers import WhenInMessageCount
from dev_tools.servers import PausingCluster, cluster_maker
from dev_tools.servers import SNormalElection
from dev_tools.servers import setup_logging

extra_logging = [dict(name="test_code", level="debug"),dict(name="SimulatedNetwork", level="warn")]
#setup_logging(extra_logging, default_level="debug")
default_level="error"
#default_level="debug"
setup_logging(default_level=default_level)
logger = logging.getLogger("test_code")


async def test_stepwise_election_1(cluster_maker):
    """

    This test is mainly for the purpose of testing the test support features implemented
    in the PausingCluster, PausingServer and various related implementations. Other tests already proved
    the basic election process using more granular control methods, this does the same kind of
    thing but using the run_till_trigger model of controlling the code. It is still somewhat
    granular, and serves as a demo of how to build tests that can run things, stop em, examine state, and continue.

    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.

    """
    cluster = cluster_maker(3)
    cluster.set_configs()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]


    cluster.test_trace.start_subtest("Starting election at node 3",
                                     test_path_str=str('/'.join(Path(__file__).parts[-2:])),
                                     test_doc_string=test_stepwise_election_1.__doc__)
    # using node 3 to make sure I don't have some sort of unintentional dependence on using node 1
    await cluster.start()
    await ts_3.start_campaign()
    out1 = WhenMessageOut(RequestVoteMessage.get_code(),
                          message_target=uri_1, flush_when_done=False)
    ts_3.add_trigger(out1)
    out2 = WhenMessageOut(RequestVoteMessage.get_code(),
                          message_target=uri_2, flush_when_done=False)
    ts_3.add_trigger(out2)
    await ts_3.run_till_triggers()
    ts_3.clear_triggers()

    # Candidate is poised to send request for vote to other two servers
    # let the messages go out
    candidate = ts_3.get_role()
    logger.debug("Candidate posted vote requests for term %d", await candidate.log.get_term())
    logger.debug("ts_1 term %d", await ts_1.log.get_term())
    logger.debug("ts_2 term %d", await ts_1.log.get_term())

    # let just these messages go
    ts_3.set_trigger(WhenAllMessagesForwarded())
    await ts_3.run_till_triggers()
    ts_3.clear_triggers()

    # Wait for the other services to send their vote responses back
    ts_1.set_trigger(WhenMessageIn(RequestVoteMessage.get_code()))
    ts_2.set_trigger(WhenMessageIn(RequestVoteMessage.get_code()))
    await ts_1.run_till_triggers()
    ts_1.clear_triggers()
    await ts_2.run_till_triggers()
    ts_2.clear_triggers()

    logger.debug("Followers have messages pending")
    ts_1.set_trigger(WhenAllInMessagesHandled())
    ts_2.set_trigger(WhenAllInMessagesHandled())
    await ts_1.run_till_triggers()
    await ts_2.run_till_triggers()

    logger.debug("Followers outgoing vote response messages pending")

    assert await ts_1.log.get_voted_for() == uri_3
    assert await ts_2.log.get_voted_for() == uri_3
    ts_1.clear_triggers()
    ts_1.set_trigger(WhenAllMessagesForwarded())
    await ts_1.run_till_triggers()
    ts_1.clear_triggers()

    ts_2.clear_triggers()
    ts_2.set_trigger(WhenAllMessagesForwarded())
    await ts_2.run_till_triggers()
    ts_2.clear_triggers()

    ts_3.clear_triggers()
    ts_3.set_trigger(WhenAllInMessagesHandled())
    await ts_3.run_till_triggers()
    ts_3.clear_triggers()
    cluster.test_trace.start_subtest("Node 3 has been sent yes vote responses from both other nodes, sending TERM_START log record")
    # Let all the messages fly until delivered
    await cluster.deliver_all_pending()
    assert ts_3.get_role_name() == "LEADER"
    assert ts_1.get_leader_uri() == uri_3
    assert ts_2.get_leader_uri() == uri_3

    logger.info("Stepwise paused election test completed")

async def test_run_to_election_1(cluster_maker):
    """
    This test is mainly for the purpose of testing the test support features implemented in the PausingCluster, PausingServer and
    related implementations. This test shows how to used two of the least granular styles of control, just allowing everything
    (except timers) proceed normally until the election is complete.

    In the first phase an election is run but having the cluster run a complete sequence that knows how to
    define the election result based on how many servers are in the quorum, and then run all nodes until
    the new TERM_START log record has been committed.

    In the second phase an election is run with a more granular style of condition checker, which can be useful
    for making things break for testing purposes. Here it is done without error in order to be demonstrate
    and validate that method.

    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """
    
    cluster = cluster_maker(3)
    cluster.set_configs()

    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]


    cluster.test_trace.start_subtest("Initial election, using fill sequence control",
                                     test_path_str=str('/'.join(Path(__file__).parts[-2:])),
                                     test_doc_string=test_run_to_election_1.__doc__)
    await cluster.start()
    await ts_3.start_campaign()
    sequence = SNormalElection(cluster, 1)
    await cluster.run_sequence(sequence)
    
    assert ts_3.get_role_name() == "LEADER"
    assert ts_1.get_leader_uri() == uri_3
    assert ts_2.get_leader_uri() == uri_3

    logger.info("-------- Initial election completion pause test completed starting reelection")
    cluster.test_trace.start_subtest("Node 3 is leader, force demoting it and pushing node 2 to start a new election, and waiting for each node to complete")
    # now have leader resign, by telling it to become follower
    await ts_3.do_demote_and_handle(None)
    assert ts_3.get_role_name() == "FOLLOWER"
    # simulate timeout on heartbeat on only one follower, so it should win
    await ts_2.do_leader_lost()
    
    ts_1.set_trigger(WhenElectionDone())
    ts_2.set_trigger(WhenElectionDone())
    ts_3.set_trigger(WhenElectionDone())
        
    await asyncio.gather(ts_1.run_till_triggers(),
                         ts_2.run_till_triggers(),
                         ts_3.run_till_triggers())
    
    ts_1.clear_triggers()
    ts_2.clear_triggers()
    ts_3.clear_triggers()

    assert ts_2.get_role_name() == "LEADER"
    assert ts_1.get_leader_uri() == uri_2
    assert ts_3.get_leader_uri() == uri_2
    cluster.test_trace.start_subtest("Node 2 is now leader, but followers have not yet seen commit, so sending heartbeat")

    await ts_2.send_heartbeats()
    await cluster.deliver_all_pending()
    logger.info("-------- Re-election test done")

    
async def test_election_timeout_1(cluster_maker):
    """
    This test operates using timers instead of the no-timers mode that most other tests use.
    It manipulates the valid range for the radom selection of election timeout value so
    that it can be known that a particluar node will timeout first, and therefore will
    win the election.

    """
    
    cluster = cluster_maker(3)
    config = cluster.build_cluster_config(election_timeout_min=0.01,
                                          election_timeout_max=0.011)
    cluster.set_configs(config)

    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]

    cfg = ts_1.cluster_config
    cfg.election_timeout_min = 0.90
    cfg.election_timeout_max = 1.0
    ts_1.change_cluster_config(cfg)
    cfg = ts_2.cluster_config
    cfg.election_timeout_min = 0.90
    cfg.election_timeout_max = 1.0
    ts_2.change_cluster_config(cfg)
    cfg = ts_3.cluster_config
    cfg.election_timeout_min = 0.01
    cfg.election_timeout_max = 0.011
    ts_3.change_cluster_config(cfg)

    cluster.test_trace.start_subtest("Initial election with timers manipulated to ensure node 3 will win",
                                     test_path_str=str('/'.join(Path(__file__).parts[-2:])),
                                     test_doc_string=test_election_timeout_1.__doc__)
    await cluster.start(timers_disabled=False)
    await ts_3.start_campaign()
    sequence = SNormalElection(cluster, 1)
    await cluster.run_sequence(sequence)
    
    assert ts_3.get_role_name() == "LEADER"
    assert ts_1.get_leader_uri() == uri_3
    assert ts_2.get_leader_uri() == uri_3

    logger.info("-------- Initial election completion, starting reelection")
    cluster.test_trace.start_subtest("Node 3 is leader know demoting it, timer values equal, poking node 2 to start election ")
    # now have leader resign, by telling it to become follower
    await ts_3.do_demote_and_handle(None)
    assert ts_3.get_role_name() == "FOLLOWER"
    # simulate timeout on heartbeat on only one follower, so it should win
    old_term = await ts_2.log.get_term()
    await ts_2.do_leader_lost()

    cfg = ts_1.cluster_config
    cfg.election_timeout_min = 0.01
    cfg.election_timeout_max = 0.011
    ts_1.change_cluster_config(cfg)
    cfg = ts_2.cluster_config
    cfg.election_timeout_min = 0.01
    cfg.election_timeout_max = 0.011
    ts_2.change_cluster_config(cfg)
    cfg = ts_3.cluster_config
    cfg.election_timeout_min = 0.01
    cfg.election_timeout_max = 0.011
    ts_3.change_cluster_config(cfg)

    # now delay for more than the timeout, should start new election with new term
    await asyncio.sleep(0.015)
    new_term = await ts_2.log.get_term()
    assert new_term == old_term + 1

    # now it should just finish, everybody should know what to do
    # with messages rendered irrelevant by restart
    ts_1.set_trigger(WhenElectionDone())
    ts_2.set_trigger(WhenElectionDone())
    ts_3.set_trigger(WhenElectionDone())
        
    await asyncio.gather(ts_1.run_till_triggers(),
                         ts_2.run_till_triggers(),
                         ts_3.run_till_triggers())
    
    ts_1.clear_triggers()
    ts_2.clear_triggers()
    ts_3.clear_triggers()

    assert ts_2.get_role_name() == "LEADER"
    assert ts_1.get_leader_uri() == uri_2
    assert ts_3.get_leader_uri() == uri_2
    logger.info("-------- Re-election timeout test done")

    cluster.test_trace.start_subtest("Node 2 is leader, testing election timeout interaction with stop flag")

    # Do the same sequence, only this time set the stopped flag on the
    # candidate to make sure the election timeout does not start another
    # election. This tests a bit of code in the hull role_after_runnner
    # method that is designed to prevent a timer from triggering code
    # in a role instance that is no longer active.
    # So, for example, a Candidate has resigned, and the hull.stop_role method 
    # has been called, and it has gotten far enough to set the stopped
    # flag, but the election timeout handler task has not yet been
    # cancelled. If the handler task fires right then it might
    # break logic that thinks the Candidate is still running.
    # So we have this mechanism to ensure that it doesn't run because
    # it is shimmed by the hull.role_after_runner method.
    
    await ts_2.do_demote_and_handle()
    await ts_1.do_leader_lost()
    assert ts_1.get_role_name() == "CANDIDATE"
    # Set the stopped flag to prevent timeout from restarting election
    # don't call stop(), it cancels the timeout
    ts_1.hull.role.stopped = True
    # now delay for more than the timeout, should start new election with new term
    old_term = await ts_1.get_term()
    assert ts_1.hull.role_async_handle is not None
    await asyncio.sleep(0.015)
    assert ts_1.get_role_name() == "CANDIDATE"
    new_term = await ts_1.get_term()
    assert new_term == old_term
    
    logger.info("-------- Election restart on timeout prevention test passed")

async def test_election_vote_once_1(cluster_maker):
    """
    Tests to make sure that followers only vote once in a single term.

    Test begins with a regular election. Next the leader and one other node are forced
    to start an election.

    The message flow is manipulated to ensure that the only follower node gets a request vote
    from only one candidate, and will vote yes.

    The message flow is again manipulated to allow the follower to get the other vote request,
    and it should reply with a no vote because it has already voted in this term.

    Finally the election is allowed to complete normally.
    
    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """
    
    cluster = cluster_maker(3)
    cluster.set_configs()

    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]


    cluster.test_trace.start_subtest("Initial election, normal",
                                     test_path_str=str('/'.join(Path(__file__).parts[-2:])),
                                     test_doc_string=test_election_vote_once_1.__doc__)
    await cluster.start()
    await ts_3.start_campaign()
    sequence = SNormalElection(cluster, 1)
    await cluster.run_sequence(sequence)
    assert ts_3.get_role_name() == "LEADER"
    assert ts_1.get_leader_uri() == uri_3
    assert ts_2.get_leader_uri() == uri_3

    logger.info("-------- Initial election completion, starting messed up re-election")

    cluster.test_trace.start_subtest("Node 3 is leader, forcing it to resign, making it and node 2 start election")

    # now have leader resign, by telling it to become follower
    await ts_3.do_demote_and_handle(None)
    assert ts_3.get_role_name() == "FOLLOWER"
    # simulate timeout on heartbeat on two followers causing
    # two candidates to try election in same term
    await ts_2.do_leader_lost()
    await ts_3.do_leader_lost()

    cluster.test_trace.start_subtest("Letting node 1 get the request vote message from node 2 only, and reply with a yes vote")
    # now let the remainging follower see only the vote request from 
    # one candidate, so let one of them send their two messages
    msg1 = await ts_2.do_next_out_msg()
    msg2 = await ts_2.do_next_out_msg()
    # just to make sure our logic is working
    assert msg1.receiver == uri_1 or msg2.receiver == uri_1

    # now let the follower cast the vote, which should be true
    await ts_1.do_next_in_msg()
    vote_yes_msg = await ts_1.do_next_out_msg()
    assert vote_yes_msg.vote == True
    await ts_2.do_next_in_msg()

    cluster.test_trace.start_subtest("Letting node 1 get the request vote message from node 3, which should get a no response")
    # now let the other candidate send requests
    msg3 = await ts_3.do_next_out_msg()
    msg4 = await ts_3.do_next_out_msg()
    # just to make sure our logic is working
    assert msg3.receiver == uri_1 or msg4.receiver == uri_1

    # now let the follower cast the vote, which should be false
    await ts_1.do_next_in_msg()
    vote_no_msg = await ts_1.do_next_out_msg()
    assert vote_no_msg.vote == False
    await ts_3.do_next_in_msg()

    # now it should just finish, everybody should know what to do

    cluster.test_trace.start_subtest("Allowing full election run to complete")
    logger.info("-------- allowing election to continue ---")
    sequence = SNormalElection(cluster, 1)
    await cluster.run_sequence(sequence)

    assert ts_2.get_role_name() == "LEADER"
    assert ts_1.get_leader_uri() == uri_2
    assert ts_3.get_leader_uri() == uri_2
    logger.info("-------- Re-election vote once test complete ---")


async def test_election_candidate_too_slow_1(cluster_maker):
    """

    This tests the logic when two candidates are active and one of them has a higher term. This
    would normally happen when election timeouts line up just right, but we fiddle the
    log of one of them directly to setup the scenario.

    The test starts with a normal election, then the leader and one other node are pushed
    to candidate. One node gets the term value increased manually.

    Next, the lower term candidate is allowed to send vote requests and the sole follower is
    allowed to receive it an reply. 

    So at this point we have node 3 with term 3 and no vote requests out, node 2 with term 2
    and one yes vote in the input queue, and node 1 having voted for node 2 in term 2.

    Before the node 2 can process the vote, however, the message is intercepted and removed from the input queue.

    Now node 3 (with the higher term) is allowed to send out its request vote messages, and node 2 is allowed
    to receive one.

    This moment is the focus of the test. Node 2 should notice the higher term and resign.

    As a bonus test we push the earlier yes vote from node 1 back on the input queue and allow
    node 2 to process it. It should just ignore it. This is probably notthe only test that hits that code.

    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """

    cluster = cluster_maker(3)
    cluster.set_configs()

    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]
    cluster.test_trace.start_subtest("Initial election, normal",
                                     test_path_str=str('/'.join(Path(__file__).parts[-2:])),
                                     test_doc_string=test_election_candidate_too_slow_1.__doc__)
    await cluster.start()
    await ts_3.start_campaign()
    sequence = SNormalElection(cluster, 1)
    await cluster.run_sequence(sequence)
    
    assert ts_3.get_role_name() == "LEADER"
    assert ts_1.get_leader_uri() == uri_3
    assert ts_2.get_leader_uri() == uri_3

    logger.info("-------- Initial election completion, starting messed up re-election")

    cluster.test_trace.start_subtest("Node 3 is leader, pushing it and node 2 to start elections, but holding messages")
    # now have leader resign, by telling it to become follower
    await ts_3.do_demote_and_handle(None)
    assert ts_3.get_role_name() == "FOLLOWER"
    # simulate timeout on heartbeat on two followers causing
    # two candidates to try election but fiddle one of them
    # to have a higher term
    await ts_2.do_leader_lost()
    term = await ts_3.log.get_term()
    await ts_3.log.set_term(term + 1)
    await ts_3.do_leader_lost()

    cluster.test_trace.start_subtest("Delivering request votes from node 2 and allowing node 1 to send yes, but holding it in node 2's queue")
    # Let the low term one send vote request first,
    # then before it receives any replies let the second
    # one send requests.
    msg1 = await ts_2.do_next_out_msg()
    msg2 = await ts_2.do_next_out_msg()
    
    logger.debug("-------- Letting first candidate win follower's vote")
    # now let the follower cast the vote, which should be true
    await ts_1.do_next_in_msg()
    vote_yes_msg_1 = await ts_1.do_next_out_msg()
    assert vote_yes_msg_1.vote == True
    # Don't let ts_2 get response, we want it to stay a candidate
    assert ts_2.get_role_name() == "CANDIDATE"
    logger.debug("-------- First candidate is now has yes vote pending ---")
    # save the pending yes vote and let the other candidate's votes in
    # instead
    cluster.test_trace.start_subtest("Removing node 1's yes vote from queue and allowing node 3 (term 2) to sent request vote messages")
    saved_vote = ts_2.in_messages.pop(0)
    # now let the second candidate requests in to the first one.
    # which should accept the new candidate because of the higher
    # term. Have to let both requests go
    msg3 = await ts_3.do_next_out_msg()
    msg4 = await ts_3.do_next_out_msg()

    # this should trigger old term candidate to resign
    # in favor of new term candidate
    await ts_2.do_next_in_msg()
    assert ts_2.get_role_name() == "FOLLOWER"
    logger.debug("-------- First candidate has accepted second candidate and resigned ")

    cluster.test_trace.start_subtest("Node 2 has resigned, replacing node 1's yes vote in queue and allowing election to proceed to completion")
    
    # Push the out of date vote back on to what used
    # to be the old candidate, just for completeness.
    # Might uncover a regression some day
    # let everbody go and check the results
    ts_2.in_messages.append(saved_vote)

    # now let everbody run and make sure election concludes
    # with second candidate elected
    sequence = SNormalElection(cluster, 1)
    await cluster.run_sequence(sequence)
    
    assert ts_3.get_role_name() == "LEADER"
    assert ts_1.get_leader_uri() == uri_3
    assert ts_2.get_leader_uri() == uri_3
    
async def test_election_candidate_log_too_old_1(cluster_maker):
    # It is possible for a candidate to have a log state that
    # is older than the state of other servers during an
    # election. The follower election code should detect that and
    # vote no on the candidate
    
    cluster = cluster_maker(3)
    heartbeat_period = 0.2
    election_timeout_min = 0.02
    election_timeout_max = 0.05
    config = cluster.build_cluster_config(heartbeat_period=heartbeat_period,
                                          election_timeout_min=election_timeout_min, 
                                          election_timeout_max=election_timeout_max)
    cluster.set_configs(config)

    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]

    await cluster.start()
    await ts_1.start_campaign()
    await cluster.run_election()
    
    assert ts_1.get_role_name() == "LEADER"
    assert ts_2.get_leader_uri() == uri_1
    assert ts_3.get_leader_uri() == uri_1

    logger.info("-------- Initial election completion, crashing follower and running command ")

    await ts_3.simulate_crash()

    # now advance the commit index
    await cluster.run_command('add 1', 1)
    # now ts_3 should have a lower prevLogIndex and so it will lose the vote
    # once we arrange the election the right way

    # just to make the logging messages clearer during debug, make sure
    # all the messages have been processed since the run_command method only
    # checks to see if a majority reported saving the log, there are also
    # commit messages that should go on next heartbeat
    await ts_1.send_heartbeats()
    await cluster.deliver_all_pending()

    logger.info("-------- Command complete,  starting messed up re-election")
    # demote leader to follower
    await ts_1.do_demote_and_handle(None)
    # restart the crashed server, which now has out of date log
    await ts_3.recover_from_crash()
    await ts_3.start_campaign()
    ts3_out_1 = await ts_3.do_next_out_msg()
    ts3_out_2 = await ts_3.do_next_out_msg()
    logger.info("-------- Target code should run on next message to ts_1,  should vote no")
    ts_1_in_1 = await ts_1.do_next_in_msg()
    assert ts_1_in_1.get_code() == RequestVoteMessage.get_code()
    ts_1_out_1 = await ts_1.do_next_out_msg()
    assert ts_1_out_1.get_code() == RequestVoteResponseMessage.get_code()
    assert ts_1_out_1.vote is False

    logger.info("-------- Vote as expected letting election finish ----")
    await cluster.deliver_all_pending()
    assert ts_3.get_role_name() != "LEADER"
    await ts_1.start_campaign()

    await cluster.deliver_all_pending()
    assert ts_1.get_role_name() == "LEADER"
    logger.info("-------- Re-election of ts_1 finished ----")
    
async def test_failed_first_election_1(cluster_maker):
    """ Let a leader win, but before the followers get his
        term_start log message, make him die (simuated). 
        Have a new election, then re-start the ex leader.
        His log will have one record in it, and so will the 
        new leader's, but the terms will be different. This
        hits a special case in follower code.
    """
    cluster = cluster_maker(3)
    cluster.set_configs()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]

    await cluster.start()
    await ts_3.start_campaign()
    out1 = WhenMessageOut(RequestVoteMessage.get_code(),
                          message_target=uri_1, flush_when_done=False)
    ts_3.add_trigger(out1)
    out2 = WhenMessageOut(RequestVoteMessage.get_code(),
                          message_target=uri_2, flush_when_done=False)
    ts_3.add_trigger(out2)
    await ts_3.run_till_triggers()
    ts_3.clear_triggers()

    # Candidate is poised to send request for vote to other two servers
    # let the messages go out
    candidate = ts_3.get_role()
    logger.debug("Candidate posted vote requests for term %d", await candidate.log.get_term())
    logger.debug("ts_1 term %d", await ts_1.log.get_term())
    logger.debug("ts_2 term %d", await ts_1.log.get_term())

    # let just these messages go
    ts_3.set_trigger(WhenAllMessagesForwarded())
    await ts_3.run_till_triggers()
    ts_3.clear_triggers()

    # Wait for the other services to send their vote responses back
    ts_1.set_trigger(WhenMessageIn(RequestVoteMessage.get_code()))
    ts_2.set_trigger(WhenMessageIn(RequestVoteMessage.get_code()))
    await ts_1.run_till_triggers()
    ts_1.clear_triggers()
    await ts_2.run_till_triggers()
    ts_2.clear_triggers()

    logger.debug("Followers have messages pending")
    ts_1.set_trigger(WhenAllInMessagesHandled())
    ts_2.set_trigger(WhenAllInMessagesHandled())
    await ts_1.run_till_triggers()
    await ts_2.run_till_triggers()

    logger.debug("Followers outgoing vote response messages pending")

    assert await ts_1.log.get_voted_for() == uri_3
    assert await ts_2.log.get_voted_for() == uri_3
    ts_1.clear_triggers()
    ts_2.clear_triggers()
    ts_3.clear_triggers()

    ts_1.set_trigger(WhenMessageOut(RequestVoteResponseMessage.get_code()))
    ts_2.set_trigger(WhenMessageOut(RequestVoteResponseMessage.get_code()))
    await ts_1.run_till_triggers()
    await ts_2.run_till_triggers()

    ts_3.set_trigger(WhenMessageOut(AppendEntriesMessage.get_code()))
    await ts_3.run_till_triggers()
    assert ts_3.get_role_name() == "LEADER"

    # Now block the leader and trigger an election
    ts_1.clear_triggers()
    ts_2.clear_triggers()
    ts_3.clear_triggers()
    await ts_3.simulate_crash()
    await ts_1.start_campaign()
    await cluster.run_election()
    assert ts_1.get_role_name() == "LEADER"
    assert await ts_3.log.get_last_term() == 1

    # now restart the ex leader and make sure his log updates
    logger.info("-------- Restarting old leader ------")
    await ts_3.recover_from_crash()
    
    await ts_1.send_heartbeats()
    # don't know how many of these are needed, because
    # timing can delay a message passed detection
    # by the simulated newtowk code, so do extras for good measure
    await cluster.deliver_all_pending()
    await cluster.deliver_all_pending()
    await cluster.deliver_all_pending()
    assert await ts_3.log.get_last_term() > 1
    
    logger.info("-------- Old leader has new first log rec, test passed ------")

