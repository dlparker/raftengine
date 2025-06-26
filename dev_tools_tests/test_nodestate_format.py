"""Unit tests for NodeStateShortestFormat delta formatting

Tests the legacy-compatible delta formatting that ensures exact output
compatibility with the original Shorthand system.
"""
import pytest
from unittest.mock import Mock
from dev_tools.trace_shorthand import NodeStateShortestFormat
from dev_tools.trace_data import SaveEvent


class TestNodeStateShortestFormat:
    """Test NodeStateShortestFormat delta calculation logic"""
    
    def setup_method(self):
        """Create mock node states for testing"""
        self.create_mock_log_rec = lambda index=0, term=1: Mock(index=index, term=term)
    
    def create_mock_node_state(self, uri="mcpy://1", role="FOLLOWER", term=1, 
                              log_index=0, log_term=1, commit_index=0,
                              on_quorum_net=True, save_event=None):
        """Helper to create consistent mock node states"""
        ns = Mock()
        ns.uri = uri
        ns.role_name = role
        ns.term = term
        ns.log_rec = self.create_mock_log_rec(log_index, log_term)
        ns.commit_index = commit_index
        ns.on_quorum_net = on_quorum_net
        ns.save_event = save_event
        ns.message = None
        ns.message_action = None
        return ns
    
    def test_role_shortening(self):
        """Test role name shortening matches legacy behavior"""
        # Test all role types
        test_cases = [
            ("FOLLOWER", "FLWR"),
            ("CANDIDATE", "CNDI"), 
            ("LEADER", "LEAD"),
            ("UNKNOWN", "FLWR")  # Default case
        ]
        
        for role_name, expected_short in test_cases:
            ns = self.create_mock_node_state(role=role_name)
            nsf = NodeStateShortestFormat(ns)
            result = nsf.format()
            assert result['role'] == expected_short
    
    def test_no_delta_without_previous_state(self):
        """Test that no delta is calculated without previous state"""
        ns = self.create_mock_node_state()
        nsf = NodeStateShortestFormat(ns)
        result = nsf.format()
        
        # All delta fields should be empty strings
        expected_delta = {
            "term": "",
            "log_last_term": "",
            "last_index": "",
            "commit_index": "",
            "network_id": ""
        }
        assert result['delta'] == expected_delta
    
    def test_term_change_delta(self):
        """Test term change creates proper delta"""
        prev_ns = self.create_mock_node_state(term=1)
        curr_ns = self.create_mock_node_state(term=2)
        
        nsf = NodeStateShortestFormat(curr_ns, prev_ns)
        result = nsf.format()
        
        assert result['delta']['term'] == "t-2"
        assert result['delta']['log_last_term'] == ""  # No log term change
        assert result['delta']['last_index'] == ""     # No log index change
        assert result['delta']['commit_index'] == ""   # No commit index change
    
    def test_log_term_change_delta(self):
        """Test log record term change creates proper delta"""
        prev_ns = self.create_mock_node_state(log_term=1)
        curr_ns = self.create_mock_node_state(log_term=2)
        
        nsf = NodeStateShortestFormat(curr_ns, prev_ns)
        result = nsf.format()
        
        assert result['delta']['log_last_term'] == "lt-2"
        assert result['delta']['term'] == ""  # No node term change
    
    def test_log_index_change_delta(self):
        """Test log record index change creates proper delta"""
        prev_ns = self.create_mock_node_state(log_index=0)
        curr_ns = self.create_mock_node_state(log_index=1)
        
        nsf = NodeStateShortestFormat(curr_ns, prev_ns)
        result = nsf.format()
        
        assert result['delta']['last_index'] == "li-1"
    
    def test_commit_index_change_delta(self):
        """Test commit index change creates proper delta"""
        prev_ns = self.create_mock_node_state(commit_index=0)
        curr_ns = self.create_mock_node_state(commit_index=1)
        
        nsf = NodeStateShortestFormat(curr_ns, prev_ns)
        result = nsf.format()
        
        assert result['delta']['commit_index'] == "ci-1"
    
    def test_network_partition_delta(self):
        """Test network partition creates proper delta"""
        prev_ns = self.create_mock_node_state(on_quorum_net=True)
        curr_ns = self.create_mock_node_state(on_quorum_net=False)
        
        nsf = NodeStateShortestFormat(curr_ns, prev_ns)
        result = nsf.format()
        
        assert result['delta']['network_id'] == "n=2"
    
    def test_network_heal_delta(self):
        """Test network heal creates proper delta"""
        prev_ns = self.create_mock_node_state(on_quorum_net=False)
        curr_ns = self.create_mock_node_state(on_quorum_net=True)
        
        nsf = NodeStateShortestFormat(curr_ns, prev_ns)
        result = nsf.format()
        
        assert result['delta']['network_id'] == "n=1"
    
    def test_partition_healed_special_case(self):
        """Test PARTITION_HEALED at first position (no prev_state)"""
        ns = self.create_mock_node_state(save_event=SaveEvent.partition_healed)
        
        nsf = NodeStateShortestFormat(ns, prev_state=None)
        result = nsf.format()
        
        # Should show network heal even without previous state
        assert result['delta']['network_id'] == "n=1"
    
    def test_multiple_changes_delta(self):
        """Test multiple simultaneous changes"""
        prev_ns = self.create_mock_node_state(
            term=1, log_index=0, log_term=1, commit_index=0, on_quorum_net=True
        )
        curr_ns = self.create_mock_node_state(
            term=2, log_index=1, log_term=2, commit_index=1, on_quorum_net=False
        )
        
        nsf = NodeStateShortestFormat(curr_ns, prev_ns)
        result = nsf.format()
        
        expected_delta = {
            "term": "t-2",
            "log_last_term": "lt-2", 
            "last_index": "li-1",
            "commit_index": "ci-1",
            "network_id": "n=2"
        }
        assert result['delta'] == expected_delta
    
    def test_format_returns_dict_not_json(self):
        """Test that format() returns dict, format_json() returns JSON string"""
        ns = self.create_mock_node_state()
        nsf = NodeStateShortestFormat(ns)
        
        dict_result = nsf.format()
        json_result = nsf.format_json()
        
        assert isinstance(dict_result, dict)
        assert isinstance(json_result, str)
        
        # JSON should be parseable back to same dict
        import json
        assert json.loads(json_result) == dict_result
    
    def test_none_log_rec_handling(self):
        """Test handling of None log_rec (should create empty LogRec)"""
        ns = self.create_mock_node_state()
        ns.log_rec = None
        
        nsf = NodeStateShortestFormat(ns)
        result = nsf.format()
        
        # Should not crash and should handle gracefully
        assert 'delta' in result
        assert isinstance(result['delta'], dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])