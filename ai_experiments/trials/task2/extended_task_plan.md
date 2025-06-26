# Extended Task: Complete Message Type Formatting

## Overview
Extend the test trace output formatting improvements to cover all Raft message types, creating a complete new-style formatting system that replaces the legacy ShorthandType1 implementation.

## Context
- **Completed**: AppendResponseShortestFormat for append_response messages
- **Existing**: AppendEntriesShortestFormat for append_entries messages  
- **Remaining**: All other Raft message types need new-style formatters
- **Goal**: Complete modernization while preserving exact output format compatibility

## Message Types to Implement
Based on the legacy ShorthandType1.message_to_trace method, the remaining message types are:
- `request_vote` → formatter needed
- `request_vote_response` → formatter needed  
- `pre_vote` → formatter needed
- `pre_vote_response` → formatter needed
- `membership_change` → formatter needed
- `membership_change_response` → formatter needed
- `transfer_power` → formatter needed
- `transfer_power_response` → formatter needed
- `snapshot` → formatter needed
- `snapshot_response` → formatter needed

## Implementation Plan

### Phase 1: Analysis and Discovery
- [ ] **Task 1**: Get recommended test list from user
  - Ask user which tests contain good examples of each message type
  - Focus search efforts on the most promising test cases
  
- [ ] **Task 2**: Examine test output files for message type examples
  - Search through .org files in captures/test_traces/no_legend_org/
  - Document existing formatting patterns for each message type
  - Map message types to their expected shortened formats

- [ ] **Task 3**: Analyze message class structures
  - Examine each message class in raftengine/messages/
  - Document the key fields that need to be formatted
  - Understand inheritance relationships (BaseMessage, LogMessage, etc.)

### Phase 2: Implementation (Iterative)
For each message type:
- [ ] **Task 4a**: Implement RequestVoteShortestFormat
- [ ] **Task 4b**: Implement RequestVoteResponseShortestFormat  
- [ ] **Task 4c**: Implement PreVoteShortestFormat
- [ ] **Task 4d**: Implement PreVoteResponseShortestFormat
- [ ] **Task 4e**: Implement MembershipChangeShortestFormat
- [ ] **Task 4f**: Implement MembershipChangeResponseShortestFormat
- [ ] **Task 4g**: Implement TransferPowerShortestFormat
- [ ] **Task 4h**: Implement TransferPowerResponseShortestFormat
- [ ] **Task 4i**: Implement SnapshotShortestFormat
- [ ] **Task 4j**: Implement SnapshotResponseShortestFormat

- [ ] **Task 5**: Update NodeStateShortestFormat
  - Register all new formatters in message_formatter_map
  - Ensure proper integration with existing system

### Phase 3: Validation and Testing
- [ ] **Task 6**: Comprehensive testing
  - Run new_format_tool.py on tests containing each message type
  - Compare output with legacy .org files for each message type
  - Verify exact format compatibility

- [ ] **Task 7**: Integration verification
  - Test with multiple message types in single test runs
  - Ensure no regressions in existing append_entries/append_response formatting
  - Validate complete replacement of legacy system

### Phase 4: Cleanup and Documentation
- [ ] **Task 8**: Code cleanup
  - Remove any unused legacy code if appropriate
  - Add documentation comments to new formatters
  - Ensure consistent code style across all formatters

## Success Criteria
- All Raft message types have dedicated shortest format classes
- Output matches legacy ShorthandType1 formatting exactly
- New system is fully integrated and extensible
- No regressions in existing functionality

## Questions for User
**Which tests should I examine first to find good examples of each message type?** I need your guidance on:
1. Tests with good `request_vote`/`request_vote_response` examples
2. Tests with `pre_vote`/`pre_vote_response` examples (if pre-vote is enabled)
3. Tests with membership change examples
4. Tests with power transfer examples  
5. Tests with snapshot examples
6. Any other tests you'd recommend for comprehensive message type coverage