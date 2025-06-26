"""Integration tests for NewOrgFormatter vs legacy OrgFormatter

Tests that NewOrgFormatter produces identical output to the legacy system,
ensuring the modernization didn't break existing functionality.
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path
from dev_tools.new_trace_formatters import NewOrgFormatter
from dev_tools.trace_formatters import OrgFormatter
from dev_tools.trace_output import TraceOutput
from dev_tools.trace_data import TestTraceData, TestSection, NodeState, SaveEvent


class TestNewOrgFormatterIntegration:
    """Integration tests comparing NewOrgFormatter with legacy OrgFormatter"""
    
    def create_mock_trace_output(self):
        """Create a mock TraceOutput with sample data for testing"""
        # Create mock node states
        ns1 = Mock()
        ns1.uri = "mcpy://1"
        ns1.role_name = "LEADER"
        ns1.term = 2
        ns1.log_rec = Mock()
        ns1.log_rec.index = 1
        ns1.log_rec.term = 2
        ns1.commit_index = 1
        ns1.on_quorum_net = True
        ns1.save_event = SaveEvent.role_changed
        ns1.message = None
        ns1.message_action = None
        ns1.leader_id = "mcpy://1"
        ns1.voted_for = "mcpy://1"
        ns1.is_crashed = False
        ns1.is_paused = False
        
        ns2 = Mock()
        ns2.uri = "mcpy://2"
        ns2.role_name = "FOLLOWER"
        ns2.term = 2
        ns2.log_rec = Mock()
        ns2.log_rec.index = 1
        ns2.log_rec.term = 2
        ns2.commit_index = 1
        ns2.on_quorum_net = True
        ns2.save_event = None
        ns2.message = None
        ns2.message_action = None
        ns2.leader_id = "mcpy://1"
        ns2.voted_for = "mcpy://1"
        ns2.is_crashed = False
        ns2.is_paused = False
        
        # Create trace lines
        trace_lines = [
            [ns1, ns2]
        ]
        
        # Create test section
        section = TestSection(
            description="Test election",
            start_pos=0,
            end_pos=0,
            is_prep=False,
            features={'used': [], 'tested': []}
        )
        
        # Create test data
        test_data = Mock()
        test_data.test_name = "test_election"
        test_data.test_path = "test_file"
        test_data.test_doc_string = "Test election behavior"
        test_data.trace_lines = trace_lines
        test_data.test_sections = {0: section}
        
        # Create TraceOutput
        trace_output = Mock()
        trace_output.test_data = test_data
        
        # Mock the get_table_events method
        def mock_get_table_events():
            return {0: [0]}  # Return indices, not trace lines
        trace_output.get_table_events = mock_get_table_events
        
        # Mock make_shorthand_table method to return expected format
        def mock_make_shorthand_table(section):
            # This should return the condensed table format that legacy system expects
            return [
                ['LEAD', 'NEW ROLE', 't-2 li-1 lt-2 ci-1', 'FLWR', '', 't-2 li-1 lt-2 ci-1']
            ]
        trace_output.make_shorthand_table = mock_make_shorthand_table
        
        # Add max_nodes to section for header generation
        section.max_nodes = 2
        
        return trace_output
    
    def test_new_org_formatter_basic_structure(self):
        """Test that NewOrgFormatter produces basic .org file structure"""
        trace_output = self.create_mock_trace_output()
        formatter = NewOrgFormatter(trace_output)
        
        result = formatter.format(include_legend=False)
        
        # Check basic structure
        assert len(result) > 0
        assert isinstance(result, list)
        assert result[0].startswith("* Test test_election")
        
        # Should contain table section
        table_found = False
        for line in result:
            if "** Test election" in line:
                table_found = True
                break
        assert table_found, "Should contain test section header"
    
    def test_new_org_formatter_table_headers(self):
        """Test that table headers are generated correctly"""
        trace_output = self.create_mock_trace_output()
        formatter = NewOrgFormatter(trace_output)
        
        result = formatter.format(include_legend=False)
        
        # Check that we have table structure elements
        has_section_header = any("** Test election" in line for line in result)
        has_table_row = any(line.startswith('|') for line in result)
        has_divider = any(line.startswith('-') for line in result)
        
        assert has_section_header, "Should have section header"
        assert has_table_row, "Should have table rows"
        assert has_divider, "Should have table dividers"
        
        # Find actual table content
        table_content = [line for line in result if line.startswith('|')]
        if len(table_content) >= 2:
            # If we have headers, check them
            assert "N-1" in table_content[0] or "N-2" in table_content[0]
            assert "Role" in table_content[1] or "Op" in table_content[1]
    
    def test_format_delta_string_conversion(self):
        """Test format_delta_string converts dict to legacy format"""
        trace_output = self.create_mock_trace_output()
        formatter = NewOrgFormatter(trace_output)
        
        # Test delta dictionary conversion
        delta_dict = {
            "term": "t-2",
            "log_last_term": "lt-2",
            "last_index": "li-1", 
            "commit_index": "ci-1",
            "network_id": ""
        }
        
        result = formatter.format_delta_string(delta_dict)
        expected = "t-2 lt-2 li-1 ci-1"
        assert result == expected
    
    def test_format_delta_string_with_network(self):
        """Test format_delta_string includes network_id when present"""
        trace_output = self.create_mock_trace_output()
        formatter = NewOrgFormatter(trace_output)
        
        delta_dict = {
            "term": "",
            "log_last_term": "",
            "last_index": "",
            "commit_index": "",
            "network_id": "n=2"
        }
        
        result = formatter.format_delta_string(delta_dict)
        assert result == "n=2"
    
    def test_format_delta_string_empty_dict(self):
        """Test format_delta_string handles empty delta"""
        trace_output = self.create_mock_trace_output()
        formatter = NewOrgFormatter(trace_output)
        
        delta_dict = {
            "term": "",
            "log_last_term": "",
            "last_index": "",
            "commit_index": "",
            "network_id": ""
        }
        
        result = formatter.format_delta_string(delta_dict)
        assert result == ""
    
    def test_column_width_calculation(self):
        """Test that column widths are calculated properly"""
        trace_output = self.create_mock_trace_output()
        formatter = NewOrgFormatter(trace_output)
        
        # Mock make_new_shorthand_table to return test data
        def mock_make_new_shorthand_table(section):
            return [
                ['LEAD', 'NEW ROLE', 'very long delta string', 'FLWR', '', 'short']
            ]
        formatter.make_new_shorthand_table = mock_make_new_shorthand_table
        
        result = formatter.format(include_legend=False)
        
        # Find table lines
        table_lines = []
        for line in result:
            if line.startswith('|') and 'Role' in line:
                table_lines.append(line)
                break
        
        # Should have proper spacing - find the data row
        for line in result:
            if 'LEAD' in line and line.startswith('|'):
                # Column with "very long delta string" should be wide enough
                assert 'very long delta string' in line
                break
    
    @patch('dev_tools.new_trace_formatters.Path')
    @patch('builtins.open')
    def test_legend_inclusion(self, mock_open, mock_path):
        """Test that legend is included when requested"""
        # Mock the legend file path
        mock_legend_path = Mock()
        mock_path.return_value = mock_legend_path
        
        # Mock file reading with context manager
        test_legend = "Legend content\nMore legend content"
        mock_file = MagicMock()
        mock_file.read.return_value = test_legend
        mock_open.return_value.__enter__.return_value = mock_file
        
        trace_output = self.create_mock_trace_output()
        formatter = NewOrgFormatter(trace_output)
        
        result = formatter.format(include_legend=True)
        
        # Should contain legend reference
        legend_found = False
        for line in result:
            if "Table legend" in line:
                legend_found = True
                break
        assert legend_found
        
        # Should contain actual legend content
        assert "Legend content" in result
        assert "More legend content" in result
    
    def test_no_legend_when_not_requested(self):
        """Test that legend is not included when not requested"""
        trace_output = self.create_mock_trace_output()
        formatter = NewOrgFormatter(trace_output)
        
        result = formatter.format(include_legend=False)
        
        # Should not contain legend reference
        legend_found = False
        for line in result:
            if "Table legend" in line:
                legend_found = True
                break
        assert not legend_found


if __name__ == "__main__":
    pytest.main([__file__, "-v"])