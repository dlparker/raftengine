#!/usr/bin/env python
import asyncio
import logging
import time
from pathlib import Path
import pytest
from raftengine.messages.request_vote import RequestVoteMessage,RequestVoteResponseMessage
from raftengine.messages.pre_vote import PreVoteMessage,PreVoteResponseMessage
from raftengine.messages.append_entries import AppendEntriesMessage, AppendResponseMessage

from dev_tools.triggers import WhenMessageOut, WhenMessageIn
from dev_tools.triggers import WhenIsLeader, WhenHasLeader
from dev_tools.triggers import WhenElectionDone
from dev_tools.triggers import WhenAllMessagesForwarded, WhenAllInMessagesHandled
from dev_tools.triggers import WhenInMessageCount
from dev_tools.pausing_cluster import PausingCluster, cluster_maker
from dev_tools.sequences import SNormalElection
from dev_tools.log_control import setup_logging
from dev_tools.features import registry, FeatureRegistry

extra_logging = [dict(name="test_code", level="debug"),dict(name="SimulatedNetwork", level="warn")]
#setup_logging(extra_logging, default_level="debug")
default_level="error"
#default_level="debug"
log_control = setup_logging()
logger = logging.getLogger("test_code")
registry = FeatureRegistry.get_registry()


async def test_stepwise_election_1(cluster_maker):
    """

    This test is mainly for the purpose of testing the test support features implemented
    in the PausingCluster, PausingServer and various related implementations. Other tests already proved
    the basic election process using more granular control methods, this does the same kind of
    thing but using the run_till_trigger model of controlling the code. It is still somewhat
    granular, and serves as a demo of how to build tests that can run things, stop em, examine state, and continue.

    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.

    """
    
    # Feature definitions - manual granular election control without pre-vote
    f_manual_election = registry.get_raft_feature("leader_election", "manual_stepwise_control")
    f_no_pre_vote = registry.get_raft_feature("leader_election", "without_pre_vote")
    f_test_infrastructure = registry.get_raft_feature("test_infrastructure", "pausing_cluster_control")
    
    cluster = cluster_maker(3)
    cluster.set_configs()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]
    cfg = ts_1.cluster_init_config
    cfg.use_pre_vote = False
    await ts_1.change_cluster_config(cfg)
    await ts_2.change_cluster_config(cfg)
    await ts_3.change_cluster_config(cfg)

    await cluster.test_trace.define_test("Testing stepwise election control with 3 nodes", logger=logger)
    
    # Section 1: Manual election trigger and stepwise control
    spec = dict(used=[f_no_pre_vote, f_manual_election], tested=[f_test_infrastructure])
    await cluster.test_trace.start_subtest("Command triggering node three to start election", features=spec)
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
    # Section 2: Election completion and term start replication
    f_term_start = registry.get_raft_feature("log_replication", "term_start_log_entry")
    spec = dict(used=[f_manual_election], tested=[f_term_start])
    await cluster.test_trace.start_subtest("Node 3 has been sent yes vote responses from both other nodes, sending TERM_START log record", features=spec)
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
    
    # Feature definitions - sequence control and automated election processes
    f_sequence_election = registry.get_raft_feature("leader_election", "sequence_controlled_election")
    f_automated_election = registry.get_raft_feature("leader_election", "automated_election_process")
    f_leader_demotion = registry.get_raft_feature("leader_election", "leader_demotion")
    f_re_election = registry.get_raft_feature("leader_election", "re_election")
    f_authorized_campaign = registry.get_raft_feature("leader_election", "authorized_campaign")
    f_heartbeat_commit = registry.get_raft_feature("log_replication", "heartbeat_commit_confirmation")
    
    cluster = cluster_maker(3)
    cluster.set_configs()

    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]

    # Make sure returning immediately from on_message works. Many tests can't handle
    # it because they want to see that the message was handled but waiting for the
    # return, and this flag breaks that.
    ts_1.deck.await_message = False
    ts_2.deck.await_message = False
    ts_3.deck.await_message = False
    await cluster.test_trace.define_test("Testing election with sequence control and triggers", logger=logger)
    
    # Section 1: Automated election using sequence control
    spec = dict(used=[f_sequence_election], tested=[f_automated_election])
    await cluster.test_trace.start_subtest("Command triggering node three to start election", features=spec)
    await cluster.start()
    await ts_3.start_campaign()
    sequence = SNormalElection(cluster, 1)
    await cluster.run_sequence(sequence)
    
    assert ts_3.get_role_name() == "LEADER"
    assert ts_1.get_leader_uri() == uri_3
    assert ts_2.get_leader_uri() == uri_3

    logger.info("-------- Initial election completion pause test completed starting reelection")
    
    # Section 2: Leader demotion and re-election with trigger coordination
    spec = dict(used=[f_leader_demotion, f_authorized_campaign], tested=[f_re_election])
    await cluster.test_trace.start_subtest("Node 3 is leader, force demoting it and pushing node 2 to start a new election, and waiting for each node to complete", features=spec)
    # now have leader resign, by telling it to become follower
    await ts_3.do_demote_and_handle(None)
    assert ts_3.get_role_name() == "FOLLOWER"
    # simulate timeout on heartbeat on only one follower, so it should win
    await ts_2.start_campaign(authorized=True)
    
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
    # Section 3: Heartbeat to confirm commit after re-election
    spec = dict(used=[f_re_election], tested=[f_heartbeat_commit])
    await cluster.test_trace.start_subtest("Node 2 is now leader, but followers have not yet seen commit, so sending heartbeat", features=spec)

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
    
    # Feature definitions - timer-based election control with timeout manipulation
    f_timeout_manipulation = registry.get_raft_feature("leader_election", "timeout_manipulation")
    f_timer_based_election = registry.get_raft_feature("leader_election", "timer_based_election")
    f_controlled_timeout_victory = registry.get_raft_feature("leader_election", "controlled_timeout_victory")
    f_leader_lost_simulation = registry.get_raft_feature("leader_election", "leader_lost_simulation")
    f_timeout_equalization = registry.get_raft_feature("leader_election", "timeout_equalization")
    
    cluster = cluster_maker(3)
    config = cluster.build_cluster_config(election_timeout_min=0.01,
                                          election_timeout_max=0.011)
    cluster.set_configs(config)

    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]

    cfg = ts_1.cluster_init_config
    cfg.election_timeout_min = 0.90
    cfg.election_timeout_max = 1.0
    ncc = await ts_1.change_cluster_config(cfg)
    assert ncc.settings.election_timeout_max == 1.0

    cfg = ts_2.cluster_init_config
    cfg.election_timeout_min = 0.90
    cfg.election_timeout_max = 1.0
    ncc = await ts_2.change_cluster_config(cfg)
    assert ncc.settings.election_timeout_max == 1.0

    cfg = ts_3.cluster_init_config
    cfg.election_timeout_min = 0.01
    cfg.election_timeout_max = 0.011
    ncc = await ts_3.change_cluster_config(cfg)
    assert ncc.settings.election_timeout_max == 0.011
    
    await cluster.test_trace.define_test("Testing election with manipulated timeouts", logger=logger)
    
    # Section 1: Timer-based election with manipulated timeouts
    spec = dict(used=[f_timeout_manipulation, f_timer_based_election], tested=[f_controlled_timeout_victory])
    await cluster.test_trace.start_subtest("Command triggering node three to start election", features=spec)
    await cluster.start(timers_disabled=False)
    await ts_3.start_campaign()
    sequence = SNormalElection(cluster, 1)
    await cluster.run_sequence(sequence)

    leader =  cluster.get_leader()
    f1 = f2 = None
    for ts in [ts_1, ts_2, ts_3]:
        if ts != leader:
            assert ts.get_leader_uri() == leader.uri
            if not f1:
                f1 = ts
            else:
                f2 = ts

    logger.info("\n\n-------- Initial election completion, starting reelection\n\n")
    
    # Section 2: Leader loss simulation with timeout equalization
    spec = dict(used=[f_leader_lost_simulation, f_timeout_equalization], tested=[f_timer_based_election])
    await cluster.test_trace.start_subtest(f"{leader.uri} is leader know demoting it, timer values equal, poking node other node to start election ", features=spec)
    # now have leader resign, by telling it to become follower
    await leader.do_demote_and_handle(None)
    assert leader.get_role_name() == "FOLLOWER"
    # simulate timeout on heartbeat on only one follower, so it should win
    old_term = await f2.log.get_term()
    await f2.do_leader_lost()

    cfg = ts_1.cluster_init_config
    cfg.election_timeout_min = 0.01
    cfg.election_timeout_max = 0.011
    await ts_1.change_cluster_config(cfg)
    cfg = ts_2.cluster_init_config
    cfg.election_timeout_min = 0.01
    cfg.election_timeout_max = 0.011
    await ts_2.change_cluster_config(cfg)
    cfg = ts_3.cluster_init_config
    cfg.election_timeout_min = 0.01
    cfg.election_timeout_max = 0.011
    await ts_3.change_cluster_config(cfg)


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

    leader =  cluster.get_leader()
    f1 = f2 = None
    for ts in [ts_1, ts_2, ts_3]:
        if ts != leader:
            assert ts.get_leader_uri() == leader.uri
            if not f1:
                f1 = ts
            else:
                f2 = ts
    logger.info("-------- Re-election timeout test done")

    await cluster.test_trace.start_subtest("Node {leader.uri} is leader, testing election timeout interaction with stop flag")

    # Do the same sequence, only this time set the stopped flag on the
    # candidate to make sure the election timeout does not start another
    # election. This tests a bit of code in the deck role_after_runnner
    # method that is designed to prevent a timer from triggering code
    # in a role instance that is no longer active.
    # So, for example, a Candidate has resigned, and the deck.stop_role method 
    # has been called, and it has gotten far enough to set the stopped
    # flag, but the election timeout handler task has not yet been
    # cancelled. If the handler task fires right then it might
    # break logic that thinks the Candidate is still running.
    # So we have this mechanism to ensure that it doesn't run because
    # it is shimmed by the deck.role_after_runner method.
    
    await leader.do_demote_and_handle()
    await f1.do_leader_lost()
    assert f1.get_role_name() == "CANDIDATE"
    # Set the stopped flag to prevent timeout from restarting election
    # don't call stop(), it cancels the timeout
    f1.deck.role.stopped = True
    # now delay for more than the timeout, should start new election with new term
    old_term = await f1.get_term()
    assert f1.deck.role_async_handle is not None
    await asyncio.sleep(0.015)
    assert f1.get_role_name() == "CANDIDATE"
    new_term = await f1.get_term()
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
    
    Prevote is disabled for this test as it makes the test code more complicated for no benefit.
    
    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """
    
    # Feature definitions - single vote per term enforcement and split vote scenarios
    f_single_vote_per_term = registry.get_raft_feature("leader_election", "single_vote_per_term")
    f_split_vote_scenario = registry.get_raft_feature("leader_election", "split_vote_scenario")
    f_message_flow_control = registry.get_raft_feature("test_infrastructure", "message_flow_control")
    f_competing_candidates = registry.get_raft_feature("leader_election", "competing_candidates")
    f_vote_rejection = registry.get_raft_feature("leader_election", "vote_rejection")
    f_vote_acceptance = registry.get_raft_feature("leader_election", "vote_acceptance")
    f_automated_election = registry.get_raft_feature("leader_election", "automated_election_process")
    f_leader_demotion = registry.get_raft_feature("leader_election", "leader_demotion")
    
    cluster = cluster_maker(3)
    config = cluster.build_cluster_config(use_pre_vote=False)
    cluster.set_configs(config)

    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]

    await cluster.test_trace.define_test("Testing single vote per term in election", logger=logger)
    
    # Section 1: Initial election setup
    spec = dict(used=[f_automated_election], tested=[])
    await cluster.test_trace.start_subtest("Command triggering node three to start election", features=spec)
    await cluster.start()
    await ts_3.start_campaign()
    sequence = SNormalElection(cluster, 1)
    await cluster.run_sequence(sequence)
    assert ts_3.get_role_name() == "LEADER"
    assert ts_1.get_leader_uri() == uri_3
    assert ts_2.get_leader_uri() == uri_3

    logger.info("-------- Initial election completion, starting messed up re-election")

    # Section 2: Setting up competing candidates scenario
    spec = dict(used=[f_leader_demotion], tested=[f_competing_candidates])
    await cluster.test_trace.start_subtest("Node 3 is leader, forcing it to resign, making it and node 2 start election", features=spec)

    # now have leader resign, by telling it to become follower
    await ts_3.do_demote_and_handle(None)
    assert ts_3.get_role_name() == "FOLLOWER"
    # simulate timeout on heartbeat on two followers causing
    # two candidates to try election in same term
    await ts_2.do_leader_lost()
    await ts_3.do_leader_lost()

    # Section 3: First vote acceptance - testing positive vote response
    spec = dict(used=[f_message_flow_control, f_competing_candidates], tested=[f_vote_acceptance])
    await cluster.test_trace.start_subtest("Letting node 1 get the request vote message from node 2 only, and reply with a yes vote", features=spec)
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

    # Section 4: Single vote per term enforcement - testing vote rejection
    spec = dict(used=[f_competing_candidates, f_message_flow_control], tested=[f_single_vote_per_term, f_vote_rejection])
    await cluster.test_trace.start_subtest("Letting node 1 get the request vote message from node 3, which should get a no response", features=spec)
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

    # Section 5: Split vote resolution - completing election after split vote
    spec = dict(used=[f_split_vote_scenario], tested=[f_automated_election])
    await cluster.test_trace.start_subtest("Allowing full election run to complete", features=spec)
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

    Prevote is disabled for this test as it makes the test code more complicated for no benefit.

    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """

    # Feature definitions - term conflict resolution and candidate resignation
    f_term_manipulation = registry.get_raft_feature("leader_election", "term_manipulation")
    f_higher_term_discovery = registry.get_raft_feature("leader_election", "higher_term_discovery")
    f_candidate_resignation = registry.get_raft_feature("leader_election", "candidate_resignation")
    f_stale_vote_handling = registry.get_raft_feature("leader_election", "stale_vote_handling")
    f_message_interception = registry.get_raft_feature("test_infrastructure", "message_interception")
    f_automated_election = registry.get_raft_feature("leader_election", "automated_election_process")
    f_leader_demotion = registry.get_raft_feature("leader_election", "leader_demotion")
    f_competing_candidates = registry.get_raft_feature("leader_election", "competing_candidates")
    f_vote_acceptance = registry.get_raft_feature("leader_election", "vote_acceptance")

    cluster = cluster_maker(3)
    config = cluster.build_cluster_config(use_pre_vote=False)
    cluster.set_configs(config)

    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]
    
    await cluster.test_trace.define_test("Testing election with candidate term conflict", logger=logger)
    
    # Section 1: Initial election setup
    spec = dict(used=[f_automated_election], tested=[])
    await cluster.test_trace.start_subtest("Command triggering node three to start election", features=spec)
    await cluster.start()
    await ts_3.start_campaign()
    sequence = SNormalElection(cluster, 1)
    await cluster.run_sequence(sequence)
    
    assert ts_3.get_role_name() == "LEADER"
    assert ts_1.get_leader_uri() == uri_3
    assert ts_2.get_leader_uri() == uri_3

    logger.info("-------- Initial election completion, starting messed up re-election")

    # Section 2: Setting up competing candidates with term manipulation
    spec = dict(used=[f_leader_demotion, f_term_manipulation], tested=[f_competing_candidates])
    await cluster.test_trace.start_subtest("Node 3 is leader, pushing it and node 2 to start elections, but holding messages", features=spec)
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

    # Section 3: Lower term candidate election attempt with message holding
    spec = dict(used=[f_competing_candidates, f_message_interception], tested=[f_vote_acceptance])
    await cluster.test_trace.start_subtest("Delivering request votes from node 2 and allowing node 1 to send yes, but holding it in node 2's queue", features=spec)
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
    # Section 4: Higher term discovery and candidate resignation
    spec = dict(used=[f_message_interception], tested=[f_higher_term_discovery, f_candidate_resignation])
    await cluster.test_trace.start_subtest("Removing node 1's yes vote from queue and allowing node 3 (term 2) to sent request vote messages", features=spec)
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

    # Section 5: Stale vote handling and election completion
    spec = dict(used=[f_candidate_resignation], tested=[f_stale_vote_handling, f_automated_election])
    await cluster.test_trace.start_subtest("Node 2 has resigned, replacing node 1's yes vote in queue and allowing election to proceed to completion", features=spec)
    
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
    """
    It is possible for a candidate to have a log state that
    is older than the state of other servers during an
    election. The follower election code should detect that and
    vote no on the candidate. This test forces that condition
    by crashing a node, then running a command with the remaining
    nodes, then restarting the crashed node and forcing it to try
    to get elected. This test is identical to test_election_candidate_log_too_old_1
    except that this version uses the pre vote logic.
    
    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """
    
    # Feature definitions - outdated log detection without pre-vote
    f_outdated_log_detection = registry.get_raft_feature("leader_election", "outdated_log_detection")
    f_log_comparison = registry.get_raft_feature("leader_election", "log_comparison")
    f_crash_recovery = registry.get_raft_feature("system_reliability", "crash_recovery")
    f_command_execution = registry.get_raft_feature("state_machine_command", "all_in_sync")
    
    cluster = cluster_maker(3)
    config = cluster.build_cluster_config(use_pre_vote=False)
    cluster.set_configs(config)
    await cluster.test_trace.define_test("Testing election with outdated candidate log (no pre-vote)", logger=logger)
    await inner_candidate_log_too_old(cluster, False, f_outdated_log_detection, f_log_comparison, f_crash_recovery, f_command_execution)
    
async def test_election_candidate_log_too_old_2(cluster_maker):
    """
    It is possible for a candidate to have a log state that
    is older than the state of other servers during an
    election. The follower election code should detect that and
    vote no on the candidate. This test forces that condition
    by crashing a node, then running a command with the remaining
    nodes, then restarting the crashed node and forcing it to try
    to get elected. This test is identical to test_election_candidate_log_too_old_1
    except that this version uses the pre vote logic.
    
    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """
    
    # Feature definitions - outdated log detection with pre-vote
    f_outdated_log_detection = registry.get_raft_feature("leader_election", "outdated_log_detection")
    f_log_comparison = registry.get_raft_feature("leader_election", "log_comparison")
    f_crash_recovery = registry.get_raft_feature("system_reliability", "crash_recovery")
    f_command_execution = registry.get_raft_feature("state_machine_command", "all_in_sync")
    f_pre_vote_with_log_check = registry.get_raft_feature("leader_election", "pre_vote_with_log_check")
    
    cluster = cluster_maker(3)
    config = cluster.build_cluster_config(use_pre_vote=True)
    cluster.set_configs(config)
    await cluster.test_trace.define_test("Testing election with outdated candidate log (with pre-vote)", logger=logger)
    await inner_candidate_log_too_old(cluster, True, f_pre_vote_with_log_check, f_log_comparison, f_crash_recovery, f_command_execution)

async def inner_candidate_log_too_old(cluster, use_pre_vote, f_main_feature, f_log_comparison, f_crash_recovery, f_command_execution):
    
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]
    
    # Section 1: Initial election setup
    f_automated_election = registry.get_raft_feature("leader_election", "automated_election_process")
    spec = dict(used=[f_automated_election], tested=[])
    await cluster.test_trace.start_subtest("Command triggering node one to start election", features=spec)
    await cluster.start()
    await ts_1.start_campaign()
    await cluster.run_election()
    
    assert ts_1.get_role_name() == "LEADER"
    assert ts_2.get_leader_uri() == uri_1
    assert ts_3.get_leader_uri() == uri_1

    logger.info("-------- Initial election completion, crashing follower and running command ")

    # Section 2: Node crash and command execution to create log divergence
    spec = dict(used=[f_crash_recovery, f_command_execution], tested=[])
    await cluster.test_trace.start_subtest("Election done, Node 1 is leader, crashing node 3 and then running a command", features=spec)
    await ts_3.simulate_crash()

    # now advance the commit index
    await cluster.run_command('add 1', 1)

    # now ts_3 should have a lower prevLogIndex and so it will lose the vote
    # once we arrange the election the right way
    logger.info("-------- Command complete,  starting messed up re-election")
    # demote leader to follower
    # Section 3: Outdated candidate election attempt and log comparison
    spec = dict(used=[f_crash_recovery], tested=[f_main_feature, f_log_comparison])
    await cluster.test_trace.start_subtest("Forcing leader to resign, restarting crashed node and forcing it into election", features=spec)
    await ts_1.do_demote_and_handle(None)
    # restart the crashed server, which now has out of date log
    await ts_3.recover_from_crash()
    await ts_3.start_campaign()
    ts3_out_1 = await ts_3.do_next_out_msg()
    ts3_out_2 = await ts_3.do_next_out_msg()
    logger.info("-------- Target code should run on next message to ts_1,  should vote no")
    ts_1.deck.cluster_ops.leader_uri = None
    ts_1_in_1 = await ts_1.do_next_in_msg()
    if not use_pre_vote:
        assert ts_1_in_1.get_code() == RequestVoteMessage.get_code()
    else:
        assert ts_1_in_1.get_code() == PreVoteMessage.get_code()
        assert not ts_1_in_1.authorized
        assert "auth=False" in str(ts_1_in_1)
    ts_1_out_1 = await ts_1.do_next_out_msg()
    if not use_pre_vote:
        assert ts_1_in_1.get_code() == RequestVoteMessage.get_code()
    else:
        assert ts_1_in_1.get_code() == PreVoteMessage.get_code()
    assert ts_1_out_1.vote is False

    logger.info("-------- Vote as expected letting election finish ----")
    await cluster.deliver_all_pending()
    assert ts_3.get_role_name() != "LEADER"
    await ts_1.start_campaign()

    await cluster.deliver_all_pending()
    assert ts_1.get_role_name() == "LEADER"
    logger.info("-------- Re-election of ts_1 finished ----")
    
async def test_election_candidate_term_too_old_1(cluster_maker):
    """
    It is possible for a candidate to have a term that is older than the term of other servers during an
    election. The follower election code should detect that and vote no on the candidate. Another test
    ensures this bahavior when pre_vote is disabled, this one tests with pre_vote enabled.

    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """
    
    # Feature definitions - outdated term detection with pre-vote
    f_outdated_term_detection = registry.get_raft_feature("leader_election", "outdated_term_detection")
    f_pre_vote_term_check = registry.get_raft_feature("leader_election", "pre_vote_term_check")
    f_crash_recovery = registry.get_raft_feature("system_reliability", "crash_recovery")
    f_authorized_campaign = registry.get_raft_feature("leader_election", "authorized_campaign")
    f_automated_election = registry.get_raft_feature("leader_election", "automated_election_process")
    
    cluster = cluster_maker(3)
    cluster.set_configs()

    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]

    await cluster.test_trace.define_test("Testing election with outdated candidate term", logger=logger)
    
    # Section 1: Initial election setup
    spec = dict(used=[f_automated_election], tested=[])
    await cluster.test_trace.start_subtest("Command triggering one three to start election", features=spec)
    await cluster.start()
    await ts_1.start_campaign()
    await cluster.run_election()
    
    assert ts_1.get_role_name() == "LEADER"
    assert ts_2.get_leader_uri() == uri_1
    assert ts_3.get_leader_uri() == uri_1

    logger.info("-------- Initial election completion, crashing follower and running command ")

    # Section 2: Leader crash and new election to advance term
    spec = dict(used=[f_crash_recovery, f_authorized_campaign], tested=[f_automated_election])
    await cluster.test_trace.start_subtest("Node 1 is leader, crashing it, then forcing a new election", features=spec)
    await ts_1.simulate_crash()

    await ts_3.start_campaign(authorized=True)
    await cluster.run_election()
    # demote leader to follower
    assert ts_3.get_role_name() == "LEADER"
    assert ts_2.get_leader_uri() == uri_3
    # Section 3: Outdated term candidate rejection via pre-vote
    spec = dict(used=[f_crash_recovery, f_authorized_campaign], tested=[f_outdated_term_detection, f_pre_vote_term_check])
    await cluster.test_trace.start_subtest("Node 3 is now leader, making node 1 start a campain which should fail because it has an old term", features=spec)
    await ts_1.recover_from_crash()
    assert await ts_1.get_term() < await ts_3.get_term()
    await ts_1.start_campaign(authorized=True)
    ts_1_out_1 = await ts_1.do_next_out_msg()
    ts_1_out_2 = await ts_1.do_next_out_msg()
    assert ts_1_out_1.get_code() == PreVoteMessage.get_code()
    assert ts_1_out_2.get_code() == PreVoteMessage.get_code()
    ts_2_in_1 = await ts_2.do_next_in_msg()
    assert ts_2_in_1.get_code() == PreVoteMessage.get_code()
    ts_2_out_1 = await ts_2.do_next_out_msg()
    assert ts_2_out_1.get_code() == PreVoteResponseMessage.get_code()
    assert ts_2_out_1.vote is False
    
async def test_failed_first_election_1(cluster_maker):
    """
    Let a leader win, but before the followers get his term_start log message, make him crash.
    Have a new election, then re-start the ex leader. His log will have one record in it, and so will the 
    new leader's, but the terms will be different. This hits a special case in follower code.

    This test runs with pre_vote disabled. test_failed_first_election_2 is identical
    except that it runs with prev_vote enabled.o
    
    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """
    
    # Feature definitions - failed election recovery without pre-vote
    f_failed_election_recovery = registry.get_raft_feature("leader_election", "failed_election_recovery")
    f_leader_crash_during_election = registry.get_raft_feature("system_reliability", "leader_crash_during_election")
    f_term_start_interruption = registry.get_raft_feature("log_replication", "term_start_interruption")
    f_log_term_conflict_resolution = registry.get_raft_feature("log_replication", "log_term_conflict_resolution")
    
    cluster = cluster_maker(3)
    config = cluster.build_cluster_config(use_pre_vote=False)
    cluster.set_configs(config)
    await cluster.test_trace.define_test("Testing election failure due to crashed leader (without pre-vote)", logger=logger)
    await inner_failed_first_election(cluster, False, f_failed_election_recovery, f_leader_crash_during_election, f_term_start_interruption, f_log_term_conflict_resolution)

async def test_failed_first_election_2(cluster_maker):
    """
    Let a leader win, but before the followers get his term_start log message, make him crash.
    Have a new election, then re-start the ex leader. His log will have one record in it, and so will the 
    new leader's, but the terms will be different. This hits a special case in follower code.

    This test runs with pre_vote enabled. test_failed_first_election_1 is identical
    except that it runs with prev_vote enabled.o
    
    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """
    
    # Feature definitions - failed election recovery with pre-vote
    f_failed_election_recovery = registry.get_raft_feature("leader_election", "failed_election_recovery_with_pre_vote")
    f_leader_crash_during_election = registry.get_raft_feature("system_reliability", "leader_crash_during_election")
    f_term_start_interruption = registry.get_raft_feature("log_replication", "term_start_interruption")
    f_log_term_conflict_resolution = registry.get_raft_feature("log_replication", "log_term_conflict_resolution")
    
    cluster = cluster_maker(3)
    config = cluster.build_cluster_config(use_pre_vote=True)
    cluster.set_configs(config)
    await cluster.test_trace.define_test("Testing election failure due to crashed leader (with pre-vote)", logger=logger)
    await inner_failed_first_election(cluster, True, f_failed_election_recovery, f_leader_crash_during_election, f_term_start_interruption, f_log_term_conflict_resolution)
    
async def inner_failed_first_election(cluster, use_pre_vote, f_main_feature, f_leader_crash, f_term_start_interruption, f_log_conflict_resolution):

    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]
    
    # Section 1: Manual election control and vote collection
    f_manual_election = registry.get_raft_feature("leader_election", "manual_stepwise_control")
    f_vote_acceptance = registry.get_raft_feature("leader_election", "vote_acceptance")
    spec = dict(used=[f_manual_election], tested=[f_vote_acceptance])
    await cluster.test_trace.start_subtest("Command triggering node three to start election", features=spec)
    await cluster.start()
    await ts_3.start_campaign()

    if use_pre_vote:
        out1 = WhenMessageIn(PreVoteResponseMessage.get_code(), message_sender=uri_2)
        ts_3.add_trigger(out1)
        out2 = WhenMessageIn(PreVoteResponseMessage.get_code(), message_sender=uri_2)
        ts_3.add_trigger(out2)
        ts_1.set_trigger(WhenMessageOut(PreVoteResponseMessage.get_code()))
        ts_2.set_trigger(WhenMessageOut(PreVoteResponseMessage.get_code()))
        
        await asyncio.gather(ts_1.run_till_triggers(),
                             ts_2.run_till_triggers(),
                             ts_3.run_till_triggers())
        
        ts_1.clear_triggers()
        ts_2.clear_triggers()
        ts_3.clear_triggers()

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
    # Section 2: Election success but term start interruption via crash
    spec = dict(used=[f_vote_acceptance], tested=[f_leader_crash, f_term_start_interruption])
    await cluster.test_trace.start_subtest("Candidate requested votes", features=spec)

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

    # make sure the leader does not deliver the append messages, it will break pre_vote,
    # doesn't matter if pre_vote is disabled
    ts_3.set_trigger(WhenMessageOut(AppendEntriesMessage.get_code(), flush_when_done=False))
    await ts_3.run_till_triggers()
    assert ts_3.get_role_name() == "LEADER"
    ts_1.clear_triggers()
    ts_2.clear_triggers()
    ts_3.clear_triggers()
    #await cluster.deliver_all_pending()
    logger.debug("Node 3 is now leader, crashing it and starting node 1 campaign")
    # Now block the leader and trigger an election
    await ts_3.simulate_crash()
    await ts_1.start_campaign(authorized=True)
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
    
async def test_power_transfer_1(cluster_maker):
    """
    Tests to check function of transfer of power.

    Test begins with a regular election. Next the leader transfers power to another node.
    That election is allowed to complete normally. That's it.
    
    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """
    
    # Feature definitions - power transfer
    f_power_transfer = registry.get_raft_feature("leader_election", "power_transfer")
    f_voluntary_step_down = registry.get_raft_feature("leader_election", "voluntary_step_down")
    f_automated_election = registry.get_raft_feature("leader_election", "automated_election_process")
    f_test_sequencing = registry.get_raft_feature("test_infrastructure", "test_sequencing")
    
    cluster = cluster_maker(3)
    config = cluster.build_cluster_config()
    cluster.set_configs(config)


    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]


    await cluster.test_trace.define_test("Testing power transfer in election", logger=logger)
    
    # Section 1: Initial election setup
    spec = dict(used=[f_automated_election, f_test_sequencing], tested=[])
    await cluster.test_trace.start_subtest("Command triggering node one to start election", features=spec)
    await cluster.start()
    await ts_1.start_campaign()
    sequence = SNormalElection(cluster, 1)
    await cluster.run_sequence(sequence)
    assert ts_1.get_role_name() == "LEADER"
    assert ts_2.get_leader_uri() == uri_1
    assert ts_3.get_leader_uri() == uri_1

    logger.info("-------- Initial election completion, doing power transfer")

    # Section 2: Power transfer initiation
    spec = dict(used=[f_power_transfer, f_voluntary_step_down], tested=[])
    await cluster.test_trace.start_subtest("Node 1 is leader, telling it to transfer power to node 2 and waiting for election", features=spec)

    await ts_1.transfer_power(ts_2.uri)
    await asyncio.sleep(0.0001)
    await cluster.deliver_all_pending()
    await asyncio.sleep(0.0001)
    await cluster.deliver_all_pending()
    assert ts_2.get_role_name() != "FOLLOWER"
    # Section 3: Power transfer completion via election
    spec = dict(used=[f_test_sequencing], tested=[f_power_transfer])
    await cluster.test_trace.start_subtest("Allowing full election run to complete", features=spec)
    logger.info("-------- allowing election to continue ---")
    sequence = SNormalElection(cluster, 1)
    await cluster.run_sequence(sequence)

    assert ts_2.get_role_name() == "LEADER"
    assert ts_1.get_leader_uri() == uri_2
    assert ts_3.get_leader_uri() == uri_2
    logger.info("-------- Re-election vote once test complete ---")


async def test_power_transfer_2(cluster_maker):
    """
    Tests to check function of transfer of power when the target node is not yet up to
    date with the leader. We arrange that by crashing the node, then running a bunch of commands,
    then recovering the node but before anything else happens start the power transfer.
    
    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    """
    
    # Feature definitions - power transfer with outdated target
    f_power_transfer_outdated = registry.get_raft_feature("leader_election", "power_transfer_with_outdated_target")
    f_crash_recovery = registry.get_raft_feature("system_reliability", "crash_recovery")
    f_command_execution = registry.get_raft_feature("log_replication", "command_execution")
    f_automated_election = registry.get_raft_feature("leader_election", "automated_election_process")
    f_test_sequencing = registry.get_raft_feature("test_infrastructure", "test_sequencing")
    f_error_handling = registry.get_raft_feature("system_reliability", "api_error_handling")
    
    cluster = cluster_maker(3)
    config = cluster.build_cluster_config()
    cluster.set_configs(config)


    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]


    await cluster.test_trace.define_test("Testing power transfer with outdated target node", logger=logger)
    
    # Section 1: Initial election setup
    spec = dict(used=[f_automated_election, f_test_sequencing], tested=[])
    await cluster.test_trace.start_subtest("Command triggering node one to start election", features=spec)
    await cluster.start()
    await ts_1.start_campaign()
    sequence = SNormalElection(cluster, 1)
    await cluster.run_sequence(sequence)
    assert ts_1.get_role_name() == "LEADER"
    assert ts_2.get_leader_uri() == uri_1
    assert ts_3.get_leader_uri() == uri_1

    logger.info("-------- Initial election completion, crashing node 2 and running some commands")

    # Section 2: Error handling validation and log divergence creation
    spec = dict(used=[f_crash_recovery, f_command_execution], tested=[f_error_handling])
    await cluster.test_trace.start_subtest("Testing power transfer error handling, node crash, and command execution", features=spec)
    
    # make sure calling transfer on something that is not  a leader doesn't work
    with pytest.raises(Exception):
        await ts_3.deck.transfer_power(ts_1.uri)
    # make sure calling transfer on invalid node doesn' work
    with pytest.raises(Exception):
        await ts_1.deck.transfer_power('foo')
    await ts_2.simulate_crash()
    await cluster.start_auto_comms()
    for i in range(0, 3):
        command_result = await ts_1.run_command("add 1")

    # Section 3: Power transfer with outdated target node
    spec = dict(used=[f_crash_recovery], tested=[f_power_transfer_outdated])
    await cluster.test_trace.start_subtest("Buncho commands run, recovering node 2 and then doing power transfer", features=spec)

    logger.info("-------- Buncho commands run, doing recover and transfer")
    await ts_2.recover_from_crash()
    await ts_1.transfer_power(ts_2.uri)
    start_time = time.time()
    while time.time() - start_time < 1.0 and ts_2.get_role_name() == "FOLLOWER":
        await asyncio.sleep(0.0001)
    assert ts_2.get_role_name() != "FOLLOWER"
    # Section 4: Power transfer completion via election
    spec = dict(used=[f_test_sequencing], tested=[f_power_transfer_outdated])
    await cluster.test_trace.start_subtest("Allowing full election run to complete", features=spec)
    logger.info("-------- allowing election to continue ---")
    sequence = SNormalElection(cluster, 1)
    await cluster.run_sequence(sequence)

    assert ts_2.get_role_name() == "LEADER"
    assert ts_1.get_leader_uri() == uri_2
    assert ts_3.get_leader_uri() == uri_2
    logger.info("-------- Re-election vote once test complete ---")

async def test_power_transfer_fails_1(cluster_maker):
    """
    Tests to see that leader goes back to accepting commands if attempt to
    update power transfer target node does not complete by election_timeout delay.

    We arrange that by crashing the targe node, then running a bunch of commands,
    then recovering the node but before anything else happens start the power transfer
    and then block the messages into the recovered node.

    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
  
   """
    
    # Feature definitions - power transfer failure handling
    f_power_transfer_timeout = registry.get_raft_feature("leader_election", "power_transfer_timeout")
    f_command_retry_logic = registry.get_raft_feature("log_replication", "command_retry_logic")
    f_network_blocking = registry.get_raft_feature("test_infrastructure", "network_blocking")
    f_crash_recovery = registry.get_raft_feature("system_reliability", "crash_recovery")
    f_command_execution = registry.get_raft_feature("log_replication", "command_execution")
    f_automated_election = registry.get_raft_feature("leader_election", "automated_election_process")
    f_test_sequencing = registry.get_raft_feature("test_infrastructure", "test_sequencing")
    
    cluster = cluster_maker(3)
    heartbeat_period = 0.001
    election_timeout_min = 0.02
    election_timeout_max = 0.03
    config = cluster.build_cluster_config(heartbeat_period=heartbeat_period,
                                          election_timeout_min=election_timeout_min, 
                                          election_timeout_max=election_timeout_max,
                                          use_pre_vote=False)
    cluster.set_configs(config)


    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]


    await cluster.test_trace.define_test("Testing power transfer failure due to timeout", logger=logger)
    
    # Section 1: Initial election setup
    spec = dict(used=[f_automated_election, f_test_sequencing], tested=[])
    await cluster.test_trace.start_subtest("Command triggering node one to start election", features=spec)
    await cluster.start()
    await ts_1.start_campaign()
    sequence = SNormalElection(cluster, 1)
    await cluster.run_sequence(sequence)
    assert ts_1.get_role_name() == "LEADER"
    assert ts_2.get_leader_uri() == uri_1
    assert ts_3.get_leader_uri() == uri_1

    logger.info("-------- Initial election completion, crashing node 2 and running some commands")

    # Section 2: Log divergence creation through crash and commands
    spec = dict(used=[f_crash_recovery, f_command_execution], tested=[])
    await cluster.test_trace.start_subtest("Crashing node 2 and executing commands to create log divergence", features=spec)
    
    await ts_2.simulate_crash()
    await cluster.start_auto_comms()
    for i in range(0, 3):
        command_result = await ts_1.run_command("add 1")
    await cluster.stop_auto_comms()

    # Section 3: Power transfer failure via network blocking and timeout
    spec = dict(used=[f_crash_recovery, f_network_blocking], tested=[f_power_transfer_timeout, f_command_retry_logic])
    await cluster.test_trace.start_subtest("Buncho commands run, recovering node 2 and blocking it and trying doing power transfer", features=spec)

    logger.info("-------- Buncho commands run, doing recover")
    await ts_2.recover_from_crash()
    ts_2.block_network()
    await ts_2.disable_timers()
    expire_time = await ts_1.transfer_power(ts_2.uri)
    assert expire_time is not None
    start_time = time.time()
    command_result = await ts_1.deck.run_command("add 1")
    assert command_result.retry 
    while time.time()  < expire_time + 0.1 and not ts_1.deck.role.accepting_commands:
        await cluster.deliver_all_pending()
        await asyncio.sleep(0.0001)
    assert ts_1.deck.role.accepting_commands
    
    # Section 4: Recovery from failed power transfer
    spec = dict(used=[f_command_execution], tested=[f_power_transfer_timeout])
    await cluster.test_trace.start_subtest("Allowing full election run to complete", features=spec)

    ts_2.unblock_network()
    await cluster.start_auto_comms()
    command_result = await ts_1.run_command("add 1")
    assert command_result.result is not None
