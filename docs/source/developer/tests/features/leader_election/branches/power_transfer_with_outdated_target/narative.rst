Power Transfer with Outdated Target tests leadership transfer when the designated successor node has an outdated log that requires synchronization before assuming leadership.

This feature validates the complex scenario where a leader initiates power transfer to a node that has fallen behind in log replication, typically due to previous network issues or crashes:

1. **Target Assessment**: Leader identifies that target node's log is outdated
2. **Log Synchronization**: Leader brings target node up to date before transfer
3. **Transfer Readiness**: System ensures target is ready to assume leadership
4. **Error Validation**: Proper error handling for invalid transfer scenarios
5. **Recovery Handling**: Target node recovery and catch-up processing

**Key Validation Points**:
- Power transfer correctly handles nodes with outdated logs
- Log synchronization occurs before leadership transfer
- Error conditions are properly validated (non-leader transfer attempts, invalid targets)
- Crashed nodes can be successfully brought up to date for transfer
- Transfer completes successfully after target node synchronization

**Error Scenarios Tested**:
- Transfer attempts by non-leader nodes are rejected
- Invalid target node URIs are handled gracefully
- Network blocking and recovery scenarios are managed correctly

This feature ensures that power transfer works reliably even when target nodes require log updates, which is common in real-world distributed systems with intermittent connectivity or node failures.