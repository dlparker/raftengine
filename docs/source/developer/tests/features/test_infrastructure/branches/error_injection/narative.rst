Error Injection provides testing infrastructure to simulate various failure scenarios and validate system resilience against unexpected errors and corruption.

This testing feature enables controlled injection of errors during message processing to verify that the Raft system handles failures gracefully:

1. **Message Explosion**: Inject exceptions during message processing
2. **Message Corruption**: Introduce data corruption into messages
3. **Selective Targeting**: Target specific message types for error injection
4. **Controlled Timing**: Inject errors at precise moments during test execution
5. **Error Recovery**: Validate system recovery after error injection

**Key Testing Capabilities**:
- Simulate message processing failures and exceptions
- Inject corruption into specific message types (AppendEntries, etc.)
- Test error handling pathways that are difficult to trigger naturally
- Validate that individual message failures don't cascade
- Verify proper error event generation and reporting
- Test system resilience under various failure conditions

**Error Types Supported**:
- `explode_on_message_code`: Throws exceptions during message processing
- `corrupt_message_with_code`: Injects invalid data into messages
- Selective targeting by message type and timing
- Controlled error injection with immediate recovery

This feature is crucial for testing edge cases and ensuring the Raft implementation remains robust under the various failure conditions that can occur in distributed systems.