# Task 2: Improve Test Trace Output Formatting

## Overview
Improve the test trace output formatting mechanism for the Raft Protocol implementation library. The task focuses on modernizing the code that converts test trace data into formatted tables.

## Context
- **Target test**: `tests/test_elections_1.py::test_election_1` 
- **Output locations**: 
  - JSON: `captures/test_traces/json/test_elections_1/test_election_1.json`
  - ORG: `captures/test_traces/no_legend_org/test_elections_1/test_election_1.org`
- **Focus message type**: AppendResponseMessage from `raftengine/messages/append_entries.py`
- **Goal**: Improve maintainability and add formatting options while preserving existing output format

## Implementation Plan

### Phase 1: Analysis and Understanding
- [ ] **Task 1**: Run new_format_tool.py and capture output
  - Execute the current implementation to see what it produces
  - Document current behavior
  
- [ ] **Task 2**: Review relationship between new and old code
  - Compare new NodeStateShortedFormat/AppendEntriesShortestFormat classes 
  - Compare with old Shorthand/ShorthandType1 classes in trace_shorthand.py
  - Identify differences and improvement opportunities

### Phase 2: Implementation  
- [ ] **Task 3**: Create MessageFormat class for append_response
  - Implement new-style MessageFormat class for "append_response" message type
  - Replicate ShorthandType1.message_to_trace method behavior for AppendResponseMessage
  - Follow patterns established by existing new-style formatters

- [ ] **Task 4**: Update NodeStateShortestFormat integration
  - Modify NodeStateShortestFormat to support the new message formatter
  - Ensure proper registration and usage of append_response formatter

### Phase 3: Validation
- [ ] **Task 5**: Test and validate formatting
  - Run new_format_tool.py again with updated code
  - Compare append_response message formatting with .org test output files
  - Ensure formatting consistency and correctness

## Key Files
- `new_format_tool.py` - Tool for testing new formatting implementation
- `dev_tools/trace_shorthand.py` - Contains old Shorthand/ShorthandType1 classes
- `raftengine/messages/append_entries.py` - Contains AppendResponseMessage class
- Target formatter classes: NodeStateShortedFormat, AppendEntriesShortestFormat

## Success Criteria
- New formatting produces identical output to legacy system for append_response messages
- Code is more maintainable and extensible for future formatting options
- All existing test trace functionality remains intact