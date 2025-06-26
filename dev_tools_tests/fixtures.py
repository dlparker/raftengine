"""Test fixtures for dev_tools tests

Provides reusable mock objects and test data for testing dev_tools functionality.
This helps avoid duplication and ensures consistent test data across test files.
"""
from unittest.mock import Mock
from dev_tools.trace_data import SaveEvent


class MockFactory:
    """Factory for creating consistent mock objects for testing"""
    
    @staticmethod
    def create_log_rec(index=0, term=1):
        """Create a mock LogRec object"""
        log_rec = Mock()
        log_rec.index = index
        log_rec.term = term
        return log_rec
    
    @staticmethod
    def create_node_state(uri="mcpy://1", role="FOLLOWER", term=1, 
                         log_index=0, log_term=1, commit_index=0,
                         on_quorum_net=True, save_event=None, 
                         message=None, message_action=None,
                         leader_id=None, voted_for=None,
                         is_crashed=False, is_paused=False):
        """Create a mock NodeState object with sensible defaults"""
        ns = Mock()
        ns.uri = uri
        ns.role_name = role
        ns.term = term
        ns.log_rec = MockFactory.create_log_rec(log_index, log_term) if log_index is not None else None
        ns.commit_index = commit_index
        ns.on_quorum_net = on_quorum_net
        ns.save_event = save_event
        ns.message = message
        ns.message_action = message_action
        ns.leader_id = leader_id or uri
        ns.voted_for = voted_for
        ns.is_crashed = is_crashed
        ns.is_paused = is_paused
        return ns
    
    @staticmethod
    def create_message(code="request_vote", sender="mcpy://1", receiver="mcpy://2",
                      term=1, **kwargs):
        """Create a mock message object"""
        msg = Mock()
        msg.code = code
        msg.sender = sender
        msg.receiver = receiver
        msg.term = term
        
        # Add message-specific fields
        if code in ("request_vote", "pre_vote"):
            msg.prevLogIndex = kwargs.get('prevLogIndex', 0)
            msg.prevLogTerm = kwargs.get('prevLogTerm', 1)
        elif code in ("request_vote_response", "pre_vote_response"):
            msg.vote = kwargs.get('vote', True)
        elif code == "append_entries":
            msg.prevLogIndex = kwargs.get('prevLogIndex', 0)
            msg.prevLogTerm = kwargs.get('prevLogTerm', 1)
            msg.entries = kwargs.get('entries', [])
            msg.commitIndex = kwargs.get('commitIndex', 0)
        elif code == "append_response":
            msg.success = kwargs.get('success', True)
            msg.maxIndex = kwargs.get('maxIndex', 0)
        elif code in ("membership_change", "membership_change_response"):
            msg.op = kwargs.get('op', 'add')
            msg.target_uri = kwargs.get('target_uri', 'mcpy://3')
            if code == "membership_change_response":
                msg.ok = kwargs.get('ok', True)
        elif code in ("transfer_power", "transfer_power_response"):
            msg.prevLogIndex = kwargs.get('prevLogIndex', 0)
            if code == "transfer_power_response":
                msg.success = kwargs.get('success', True)
        elif code in ("snapshot", "snapshot_response"):
            msg.prevLogIndex = kwargs.get('prevLogIndex', 0)
            if code == "snapshot_response":
                msg.success = kwargs.get('success', True)
        
        return msg
    
    @staticmethod
    def create_test_section(description="Test section", start_pos=0, end_pos=None,
                           is_prep=False, features=None):
        """Create a mock TestSection object"""
        section = Mock()
        section.description = description
        section.start_pos = start_pos
        section.end_pos = end_pos
        section.is_prep = is_prep
        section.features = features or {'used': [], 'tested': []}
        section.max_nodes = 3  # Default for most tests
        return section


class TestScenarios:
    """Pre-built test scenarios for common Raft situations"""
    
    @staticmethod
    def leader_election_scenario():
        """Create a simple leader election scenario"""
        # Initial state: all followers
        ns1_initial = MockFactory.create_node_state(
            uri="mcpy://1", role="FOLLOWER", term=1
        )
        ns2_initial = MockFactory.create_node_state(
            uri="mcpy://2", role="FOLLOWER", term=1
        )
        ns3_initial = MockFactory.create_node_state(
            uri="mcpy://3", role="FOLLOWER", term=1
        )
        
        # Node 1 becomes candidate
        ns1_candidate = MockFactory.create_node_state(
            uri="mcpy://1", role="CANDIDATE", term=2,
            save_event=SaveEvent.role_changed
        )
        ns2_follower = MockFactory.create_node_state(
            uri="mcpy://2", role="FOLLOWER", term=2
        )
        ns3_follower = MockFactory.create_node_state(
            uri="mcpy://3", role="FOLLOWER", term=2
        )
        
        # Node 1 becomes leader
        ns1_leader = MockFactory.create_node_state(
            uri="mcpy://1", role="LEADER", term=2,
            save_event=SaveEvent.role_changed
        )
        
        return {
            'trace_lines': [
                [ns1_initial, ns2_initial, ns3_initial],
                [ns1_candidate, ns2_follower, ns3_follower],
                [ns1_leader, ns2_follower, ns3_follower]
            ],
            'sections': {
                0: MockFactory.create_test_section("Leader election test", 0, 2)
            }
        }
    
    @staticmethod
    def message_exchange_scenario():
        """Create a scenario with message exchanges"""
        # Node 1 sends request_vote to node 2
        vote_msg = MockFactory.create_message(
            code="request_vote", sender="mcpy://1", receiver="mcpy://2",
            term=2, prevLogIndex=0, prevLogTerm=1
        )
        
        ns1_sender = MockFactory.create_node_state(
            uri="mcpy://1", role="CANDIDATE", term=2,
            save_event=SaveEvent.message_op, message=vote_msg, message_action="sent"
        )
        ns2_receiver = MockFactory.create_node_state(
            uri="mcpy://2", role="FOLLOWER", term=2
        )
        
        # Node 2 responds with vote
        vote_response = MockFactory.create_message(
            code="request_vote_response", sender="mcpy://2", receiver="mcpy://1",
            term=2, vote=True
        )
        
        ns1_receiver = MockFactory.create_node_state(
            uri="mcpy://1", role="CANDIDATE", term=2
        )
        ns2_sender = MockFactory.create_node_state(
            uri="mcpy://2", role="FOLLOWER", term=2,
            save_event=SaveEvent.message_op, message=vote_response, message_action="sent"
        )
        
        return {
            'trace_lines': [
                [ns1_sender, ns2_receiver],
                [ns1_receiver, ns2_sender]
            ],
            'sections': {
                0: MockFactory.create_test_section("Message exchange test", 0, 1)
            }
        }
    
    @staticmethod
    def network_partition_scenario():
        """Create a scenario with network partition"""
        # Normal state
        ns1_normal = MockFactory.create_node_state(
            uri="mcpy://1", role="LEADER", term=2, on_quorum_net=True
        )
        ns2_normal = MockFactory.create_node_state(
            uri="mcpy://2", role="FOLLOWER", term=2, on_quorum_net=True
        )
        
        # Node 2 gets partitioned
        ns1_still_normal = MockFactory.create_node_state(
            uri="mcpy://1", role="LEADER", term=2, on_quorum_net=True
        )
        ns2_partitioned = MockFactory.create_node_state(
            uri="mcpy://2", role="FOLLOWER", term=2, on_quorum_net=False,
            save_event=SaveEvent.net_partition
        )
        
        # Network heals
        ns1_healed = MockFactory.create_node_state(
            uri="mcpy://1", role="LEADER", term=2, on_quorum_net=True
        )
        ns2_healed = MockFactory.create_node_state(
            uri="mcpy://2", role="FOLLOWER", term=2, on_quorum_net=True,
            save_event=SaveEvent.partition_healed
        )
        
        return {
            'trace_lines': [
                [ns1_normal, ns2_normal],
                [ns1_still_normal, ns2_partitioned],
                [ns1_healed, ns2_healed]
            ],
            'sections': {
                0: MockFactory.create_test_section("Network partition test", 0, 2)
            }
        }


class MessageTestCases:
    """Test cases for different message types and directions"""
    
    @staticmethod
    def all_message_types():
        """Return test cases for all supported message types"""
        return [
            {
                'name': 'request_vote_outgoing',
                'message': MockFactory.create_message('request_vote', 'mcpy://1', 'mcpy://2'),
                'node_uri': 'mcpy://1',  # Sender matches node
                'expected_prefix': 'poll+N-2'
            },
            {
                'name': 'request_vote_incoming', 
                'message': MockFactory.create_message('request_vote', 'mcpy://1', 'mcpy://2'),
                'node_uri': 'mcpy://2',  # Receiver matches node
                'expected_prefix': 'N-1+poll'
            },
            {
                'name': 'request_vote_response',
                'message': MockFactory.create_message('request_vote_response', 'mcpy://2', 'mcpy://1'),
                'node_uri': 'mcpy://2',  # Sender matches node
                'expected_prefix': 'vote+N-1'
            },
            {
                'name': 'append_entries_outgoing',
                'message': MockFactory.create_message('append_entries', 'mcpy://1', 'mcpy://2',
                                                    entries=[], commitIndex=0),
                'node_uri': 'mcpy://1',  # Sender matches node
                'expected_prefix': 'ae+N-2'
            },
            {
                'name': 'append_response',
                'message': MockFactory.create_message('append_response', 'mcpy://2', 'mcpy://1'),
                'node_uri': None,  # append_response doesn't use node_state
                'expected_prefix': 'N-2+ae_reply'
            }
        ]