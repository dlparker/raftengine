"""
Unit tests for readable PlantUML message formatters.
Tests the new readable message formatters and ReadablePUMLFormatter class.
"""

import unittest
import sys
from pathlib import Path

# Add dev_tools to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "dev_tools"))

from puml_message_formatters import (
    RequestVoteReadableFormat, 
    RequestVoteResponseReadableFormat, 
    AppendEntriesReadableFormat,
    AppendResponseReadableFormat,
    PreVoteReadableFormat,
    PreVoteResponseReadableFormat,
    READABLE_MESSAGE_FORMATTERS
)
from trace_formatters import ReadablePUMLFormatter


class MockMessage:
    """Mock message class for testing formatters"""
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class TestReadableMessageFormatters(unittest.TestCase):
    """Test cases for readable message formatters"""

    def test_request_vote_formatter(self):
        """Test RequestVoteReadableFormat"""
        message = MockMessage(
            code="request_vote",
            term=1,
            prevLogIndex=0,
            prevLogTerm=1,
            sender="mcpy://1",
            receiver="mcpy://2"
        )
        
        formatter = RequestVoteReadableFormat(message)
        result = formatter.format()
        expected = "RequestVote(term=1, lastIndex=0, lastTerm=1)"
        self.assertEqual(result, expected)

    def test_request_vote_response_formatter(self):
        """Test RequestVoteResponseReadableFormat"""
        message = MockMessage(
            code="request_vote_response",
            vote=True,
            sender="mcpy://2",
            receiver="mcpy://1"
        )
        
        formatter = RequestVoteResponseReadableFormat(message)
        result = formatter.format()
        expected = "VoteResponse(granted=True)"
        self.assertEqual(result, expected)

    def test_append_entries_formatter_heartbeat(self):
        """Test AppendEntriesReadableFormat with no entries (heartbeat)"""
        message = MockMessage(
            code="append_entries",
            term=1,
            prevLogIndex=0,
            prevLogTerm=0,
            entries=[],
            commitIndex=0,
            sender="mcpy://1",
            receiver="mcpy://2"
        )
        
        formatter = AppendEntriesReadableFormat(message)
        result = formatter.format()
        expected = "AppendEntries(term=1, prevIndex=0, prevTerm=0, heartbeat, commitIndex=0)"
        self.assertEqual(result, expected)

    def test_append_entries_formatter_single_entry(self):
        """Test AppendEntriesReadableFormat with one entry"""
        message = MockMessage(
            code="append_entries",
            term=2,
            prevLogIndex=1,
            prevLogTerm=1,
            entries=["entry1"],
            commitIndex=1,
            sender="mcpy://1",
            receiver="mcpy://2"
        )
        
        formatter = AppendEntriesReadableFormat(message)
        result = formatter.format()
        expected = "AppendEntries(term=2, prevIndex=1, prevTerm=1, 1 entry, commitIndex=1)"
        self.assertEqual(result, expected)

    def test_append_entries_formatter_multiple_entries(self):
        """Test AppendEntriesReadableFormat with multiple entries"""
        message = MockMessage(
            code="append_entries",
            term=2,
            prevLogIndex=1,
            prevLogTerm=1,
            entries=["entry1", "entry2", "entry3"],
            commitIndex=1,
            sender="mcpy://1",
            receiver="mcpy://2"
        )
        
        formatter = AppendEntriesReadableFormat(message)
        result = formatter.format()
        expected = "AppendEntries(term=2, prevIndex=1, prevTerm=1, 3 entries, commitIndex=1)"
        self.assertEqual(result, expected)

    def test_append_response_formatter(self):
        """Test AppendResponseReadableFormat"""
        message = MockMessage(
            code="append_response",
            success=True,
            maxIndex=2,
            sender="mcpy://2",
            receiver="mcpy://1"
        )
        
        formatter = AppendResponseReadableFormat(message)
        result = formatter.format()
        expected = "AppendResponse(success=True, maxIndex=2)"
        self.assertEqual(result, expected)

    def test_pre_vote_formatter(self):
        """Test PreVoteReadableFormat"""
        message = MockMessage(
            code="pre_vote",
            term=1,
            prevLogIndex=0,
            prevLogTerm=1,
            sender="mcpy://1",
            receiver="mcpy://2"
        )
        
        formatter = PreVoteReadableFormat(message)
        result = formatter.format()
        expected = "PreVoteRequest(term=1, lastIndex=0, lastTerm=1)"
        self.assertEqual(result, expected)

    def test_pre_vote_response_formatter(self):
        """Test PreVoteResponseReadableFormat"""
        message = MockMessage(
            code="pre_vote_response",
            vote=False,
            sender="mcpy://2",
            receiver="mcpy://1"
        )
        
        formatter = PreVoteResponseReadableFormat(message)
        result = formatter.format()
        expected = "PreVoteResponse(granted=False)"
        self.assertEqual(result, expected)

    def test_formatter_mapping(self):
        """Test that all message types are mapped to formatters"""
        expected_codes = {
            'request_vote',
            'request_vote_response', 
            'append_entries',
            'append_response',
            'pre_vote',
            'pre_vote_response',
            'membership_change',
            'membership_change_response',
            'transfer_power',
            'transfer_power_response',
            'snapshot',
            'snapshot_response'
        }
        
        self.assertEqual(set(READABLE_MESSAGE_FORMATTERS.keys()), expected_codes)

    def test_wrong_message_type_error(self):
        """Test that formatters reject wrong message types"""
        message = MockMessage(code="append_entries", term=1, prevLogIndex=0, prevLogTerm=0, entries=[], commitIndex=0)
        
        with self.assertRaises(Exception) as context:
            RequestVoteReadableFormat(message)
        
        self.assertIn("not a request_vote message", str(context.exception))


class TestReadablePUMLFormatter(unittest.TestCase):
    """Test cases for ReadablePUMLFormatter class"""

    def setUp(self):
        """Set up test fixtures"""
        # Create minimal test data structure
        class MockTestData:
            def __init__(self):
                self.test_name = "test_readable_format"
                self.trace_lines = []
        
        class MockTraceOutput:
            def __init__(self):
                self.test_data = MockTestData()
        
        class MockSection:
            def __init__(self):
                self.start_pos = 0
                self.end_pos = 0
        
        self.trace_output = MockTraceOutput()
        self.section = MockSection()
        self.formatter = ReadablePUMLFormatter(self.trace_output)

    def test_puml_formatter_initialization(self):
        """Test ReadablePUMLFormatter can be initialized"""
        self.assertIsNotNone(self.formatter)
        self.assertEqual(self.formatter.trace_output, self.trace_output)

    def test_format_message_readable(self):
        """Test format_message_readable method"""
        message = MockMessage(
            code="request_vote",
            term=1,
            prevLogIndex=0,
            prevLogTerm=1
        )
        
        result = self.formatter.format_message_readable(message, None)
        expected = "RequestVote(term=1, lastIndex=0, lastTerm=1)"
        self.assertEqual(result, expected)

    def test_format_basic_structure(self):
        """Test that format method produces valid PlantUML structure"""
        # Set up minimal trace data
        self.trace_output.test_data.trace_lines = [[]]
        
        result = self.formatter.format(self.section)
        
        # Check basic PlantUML structure
        self.assertIsInstance(result, list)
        self.assertTrue(any("@startuml" in line for line in result))
        self.assertTrue(any("@enduml" in line for line in result))
        self.assertTrue(any("title" in line for line in result))
        self.assertTrue(any("legend" in line for line in result))

    def test_format_empty_trace(self):
        """Test formatting with empty trace data"""
        self.trace_output.test_data.trace_lines = []
        
        result = self.formatter.format(self.section)
        
        # Should still produce valid PlantUML even with no data
        self.assertIsInstance(result, list)
        self.assertTrue(len(result) > 10)  # Should have basic structure


class TestFormatterComparison(unittest.TestCase):
    """Integration tests comparing readable vs compact formats"""

    def test_readable_vs_compact_sample(self):
        """Test that readable format is more descriptive than compact"""
        message = MockMessage(
            code="request_vote",
            term=1,
            prevLogIndex=0,
            prevLogTerm=1,
            sender="mcpy://1",
            receiver="mcpy://2"
        )
        
        # Readable format
        readable_formatter = RequestVoteReadableFormat(message)
        readable_result = readable_formatter.format()
        
        # Check that readable format includes full parameter names
        self.assertIn("term=", readable_result)
        self.assertIn("lastIndex=", readable_result)
        self.assertIn("lastTerm=", readable_result)
        self.assertIn("RequestVote", readable_result)
        
        # Check that it doesn't use abbreviations
        self.assertNotIn("t-", readable_result)
        self.assertNotIn("li-", readable_result)
        self.assertNotIn("lt-", readable_result)
        self.assertNotIn("poll", readable_result)


if __name__ == '__main__':
    # Create sample PlantUML files for manual comparison
    readable_sample = """@startuml
title Readable Raft Election Sequence (Sample)

participant "Node 1" as n1 order 10 #Lightgreen
participant "Node 2" as n2 order 20 #Lightgreen  
participant "Node 3" as n3 order 30 #Lightgreen

n1 -> n1: Becomes CANDIDATE
note left of n1: Term: 1
n1 -> n2: RequestVote(term=1, lastIndex=0, lastTerm=1)
n1 -> n3: RequestVote(term=1, lastIndex=0, lastTerm=1)
n2 -> n1: VoteResponse(granted=True)
n3 -> n1: VoteResponse(granted=True)
n1 -> n1: Becomes LEADER
n1 -> n2: AppendEntries(term=1, prevIndex=0, prevTerm=0, heartbeat, commitIndex=0)
n1 -> n3: AppendEntries(term=1, prevIndex=0, prevTerm=0, heartbeat, commitIndex=0)

legend right
  |<#Lightgreen>| Raft Node |
  |FOLLOWER| Follower Role |
  |CANDIDATE| Candidate Role |
  |LEADER| Leader Role |
endlegend
@enduml"""

    compact_sample = """@startuml
title Compact Raft Election Sequence (Sample)

participant "Node 1 (N-1)" as n1 order 10 #Lightgreen
participant "Node 2 (N-2)" as n2 order 20 #Lightgreen
participant "Node 3 (N-3)" as n3 order 30 #Lightgreen

n1 -> n1: NEW ROLE (CANDIDATE)
note left of n1: Term: t-1
n1 -> n2: poll t-1 li-0 lt-1
n1 -> n3: poll t-1 li-0 lt-1
n2 -> n1: vote yes-True
n3 -> n1: vote yes-True
n1 -> n1: NEW ROLE (LEADER)
n1 -> n2: ae t-1 i-0 lt-0 e-0 c-0
n1 -> n3: ae t-1 i-0 lt-0 e-0 c-0

legend right
  |<#Lightgreen>| Raft Engine Node |
  |FLWR| Follower Role |
  |CNDI| Candidate Role |
  |LEAD| Leader Role |
  |poll| Request Vote |
  |vote| Vote Response |
  |ae| Append Entries |
endlegend
@enduml"""

    # Save samples for comparison
    Path("sample_readable_test.puml").write_text(readable_sample)
    Path("sample_compact_test.puml").write_text(compact_sample)
    
    print("Sample PlantUML files created for comparison:")
    print("- sample_readable_test.puml (new readable format)")
    print("- sample_compact_test.puml (original compact format)")
    print()
    
    # Run the tests
    unittest.main()