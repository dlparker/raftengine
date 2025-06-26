"""Unit tests for message formatter direction logic

Tests the crucial directional formatting that was the source of major bugs
during development. These tests would have caught the N-1+poll vs poll+N-2 
direction confusion early.
"""
import pytest
import json
from unittest.mock import Mock
from dev_tools.trace_shorthand import (
    NodeStateShortestFormat, 
    RequestVoteShortestFormat,
    RequestVoteResponseShortestFormat,
    AppendEntriesShortestFormat,
    AppendResponseShortestFormat
)
from dev_tools.trace_data import NodeState, SaveEvent


class TestMessageFormatterDirections:
    """Test message direction logic that caused major debugging issues"""
    
    def setup_method(self):
        """Create mock node states for testing"""
        # Mock node state for node 1
        self.node1_state = Mock()
        self.node1_state.uri = "mcpy://1"
        self.node1_state.role_name = "CANDIDATE"
        self.node1_state.term = 2
        self.node1_state.log_rec = Mock()
        self.node1_state.log_rec.index = 0
        self.node1_state.log_rec.term = 1
        self.node1_state.commit_index = 0
        self.node1_state.save_event = SaveEvent.message_op
        self.node1_state.on_quorum_net = True
        
        # Mock node state for node 2
        self.node2_state = Mock()
        self.node2_state.uri = "mcpy://2"
        self.node2_state.role_name = "FOLLOWER"
        self.node2_state.term = 1
        self.node2_state.log_rec = Mock()
        self.node2_state.log_rec.index = 0
        self.node2_state.log_rec.term = 1
        self.node2_state.commit_index = 0
        self.node2_state.save_event = SaveEvent.message_op
        self.node2_state.on_quorum_net = True

    def test_request_vote_outgoing_direction(self):
        """Test request_vote shows as 'poll+N-2' when sent from node 1"""
        # Create outgoing request_vote message from node 1 to node 2
        message = Mock()
        message.code = "request_vote"
        message.sender = "mcpy://1"
        message.receiver = "mcpy://2"
        message.term = 2
        message.prevLogIndex = 0
        message.prevLogTerm = 1
        
        # Test with node_state (outgoing)
        formatter = RequestVoteShortestFormat(message, self.node1_state)
        result = formatter.format()
        
        assert result == "poll+N-2 t-2 li-0 lt-1"
        
    def test_request_vote_incoming_direction(self):
        """Test request_vote shows as 'N-1+poll' when received by node 2"""
        # Create incoming request_vote message from node 1 to node 2
        message = Mock()
        message.code = "request_vote"
        message.sender = "mcpy://1"
        message.receiver = "mcpy://2"
        message.term = 2
        message.prevLogIndex = 0
        message.prevLogTerm = 1
        
        # Test without node_state match (incoming)
        formatter = RequestVoteShortestFormat(message, self.node2_state)
        result = formatter.format()
        
        assert result == "N-1+poll t-2 li-0 lt-1"

    def test_request_vote_response_directions(self):
        """Test request_vote_response direction logic"""
        message = Mock()
        message.code = "request_vote_response"
        message.sender = "mcpy://2"
        message.receiver = "mcpy://1"
        message.vote = True
        
        # Outgoing from node 2
        formatter = RequestVoteResponseShortestFormat(message, self.node2_state)
        result = formatter.format()
        assert result == "vote+N-1 yes-True"
        
        # Incoming to node 1
        formatter = RequestVoteResponseShortestFormat(message, self.node1_state)
        result = formatter.format()
        assert result == "N-2+vote yes-True"

    def test_append_entries_directions(self):
        """Test append_entries direction logic"""
        message = Mock()
        message.code = "append_entries"
        message.sender = "mcpy://1"
        message.receiver = "mcpy://2"
        message.term = 2
        message.prevLogIndex = 0
        message.prevLogTerm = 1
        message.entries = []
        message.commitIndex = 0
        
        # Outgoing from node 1
        formatter = AppendEntriesShortestFormat(message, self.node1_state)
        result = formatter.format()
        assert result == "ae+N-2 t-2 i-0 lt-1 e-0 c-0"
        
        # Incoming to node 2
        formatter = AppendEntriesShortestFormat(message, self.node2_state)  
        result = formatter.format()
        assert result == "N-1+ae t-2 i-0 lt-1 e-0 c-0"

    def test_append_response_always_incoming(self):
        """Test append_response always shows as incoming (N-sender+code)"""
        message = Mock()
        message.code = "append_response"
        message.sender = "mcpy://2"
        message.receiver = "mcpy://1"
        message.success = True
        message.maxIndex = 0
        
        # append_response doesn't take node_state parameter
        formatter = AppendResponseShortestFormat(message)
        result = formatter.format()
        assert result == "N-2+ae_reply ok-True mi-0"

    def test_nodestate_shortest_format_integration(self):
        """Test NodeStateShortestFormat with message formatters"""
        # Create message
        message = Mock()
        message.code = "request_vote"
        message.sender = "mcpy://1"
        message.receiver = "mcpy://2"
        message.term = 2
        message.prevLogIndex = 0
        message.prevLogTerm = 1
        
        # Attach message to node state
        self.node1_state.message = message
        self.node1_state.message_action = "sent"
        
        # Test NodeStateShortestFormat
        nsf = NodeStateShortestFormat(self.node1_state)
        result = nsf.format()
        
        # Should show outgoing direction since message.sender == node_state.uri
        assert result['op'] == "poll+N-2 t-2 li-0 lt-1"
        assert result['role'] == "CNDI"
        
    def test_nodestate_format_without_node_state_context(self):
        """Test NodeStateShortestFormat when node_state doesn't match message sender"""
        # Create message from node 1
        message = Mock()
        message.code = "request_vote" 
        message.sender = "mcpy://1"
        message.receiver = "mcpy://2"
        message.term = 2
        message.prevLogIndex = 0
        message.prevLogTerm = 1
        
        # Attach to node 2's state (receiving end)
        self.node2_state.message = message
        self.node2_state.message_action = "handled_in"
        
        nsf = NodeStateShortestFormat(self.node2_state)
        result = nsf.format()
        
        # Should show incoming direction since message.sender != node_state.uri
        assert result['op'] == "N-1+poll t-2 li-0 lt-1"
        assert result['role'] == "FLWR"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])