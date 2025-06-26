# Dev Tools Test Suite

This directory contains comprehensive unit and integration tests for the `dev_tools/` components.

## Overview

The dev_tools test suite was created to provide confidence in the test infrastructure itself. As noted during development: "It would be pretty funny if I needed to build a unit test suit for my unit test support code, but I'm thinking that might be the case." These tests ensure that the critical dev_tools functionality works correctly and catches bugs early.

## Test Structure

### Core Test Files

- **`test_message_formatters.py`** - Unit tests for message formatter direction logic
  - Tests the crucial `poll+N-2` vs `N-1+poll` direction formatting
  - Would have caught the major direction bug that caused extensive debugging
  - Covers all 12 Raft message types (append_entries, request_vote, etc.)

- **`test_nodestate_format.py`** - Tests for NodeStateShortestFormat delta calculation
  - Role shortening (FOLLOWER → FLWR, CANDIDATE → CNDI, LEADER → LEAD)
  - Delta calculation logic for term, log, and network changes
  - Legacy compatibility with Shorthand formatting system

- **`test_new_org_formatter.py`** - Integration tests for NewOrgFormatter
  - Ensures NewOrgFormatter produces identical output to legacy OrgFormatter
  - Tests table generation, column width calculation, legend inclusion
  - Validates the modernization didn't break existing functionality

### Support Files

- **`fixtures.py`** - Reusable mock objects and test scenarios
  - `MockFactory` for creating consistent test objects
  - `TestScenarios` for pre-built Raft situations (elections, partitions, etc.)
  - `MessageTestCases` for comprehensive message type testing

- **`test_runner.py`** - Automated test runner with coverage support
- **`run_coverage.sh`** - Simple script for coverage reports

## Running Tests

### Basic Test Execution
```bash
# Run all tests
python dev_tools_tests/test_runner.py

# Run specific test file
python -m pytest dev_tools_tests/test_message_formatters.py -v
```

### Coverage Reports

#### HTML Coverage (Separate from raftengine coverage)
```bash
# Generate HTML coverage report for dev_tools only
./dev_tools_tests/run_coverage.sh --html

# View the report
open dev_tools_tests/htmlcov/index.html
```

#### Terminal Coverage
```bash
# Quick terminal coverage report
./dev_tools_tests/run_coverage.sh
```

### Alternative Coverage with test_runner.py
```bash
# Using the Python test runner (if coverage config issues are resolved)
python dev_tools_tests/test_runner.py --html
python dev_tools_tests/test_runner.py --cov
```

## Coverage Configuration

The test suite uses separate coverage configuration from the main raftengine project:

- **`dev_tools_tests/.coveragerc`** - Coverage config for dev_tools only
- **`dev_tools_tests/.gitignore`** - Excludes coverage artifacts
- **HTML reports** go to `dev_tools_tests/htmlcov/` (separate from main `htmlcov/`)
- **Source focus** on `dev_tools/` directory only

### Coverage Highlights

Current coverage focuses on the modernized formatting system:
- **`new_trace_formatters.py`** - 99% coverage 
- **`trace_shorthand.py`** - 44% coverage (covers new NodeStateShortestFormat)
- **`trace_data.py`** - 65% coverage (core data structures)

## Key Test Cases

### Message Direction Logic Tests
These tests would have prevented the major debugging issue where outgoing messages showed as `N-1+poll` instead of `poll+N-2`:

```python
def test_request_vote_outgoing_direction(self):
    # Should show 'poll+N-2' when sent from node 1
    assert result == "poll+N-2 t-2 li-0 lt-1"

def test_request_vote_incoming_direction(self):  
    # Should show 'N-1+poll' when received by node 2
    assert result == "N-1+poll t-2 li-0 lt-1"
```

### Delta Formatting Tests
Ensure legacy compatibility:
```python
def test_multiple_changes_delta(self):
    expected_delta = {
        "term": "t-2",
        "log_last_term": "lt-2", 
        "last_index": "li-1",
        "commit_index": "ci-1",
        "network_id": "n=2"
    }
```

## Benefits

1. **Early Bug Detection** - Unit tests catch direction logic errors before integration testing
2. **Refactoring Confidence** - Safe to modernize trace formatting system
3. **Documentation** - Tests serve as examples of expected behavior
4. **Regression Prevention** - Prevents reintroduction of solved bugs

## Future Enhancements

Potential areas for expansion:
- Tests for `.rst` and `.puml` formatters when implemented
- Performance tests for large trace files
- Property-based testing for Raft scenarios
- Integration tests with actual test trace data

## Test Architecture Notes

The test suite uses a factory pattern with `MockFactory` to create consistent test objects, avoiding duplication and ensuring reliable test data across all test files. This approach makes it easy to add new test scenarios while maintaining consistency.