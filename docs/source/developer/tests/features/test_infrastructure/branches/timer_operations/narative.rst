Timer Operations provide testing infrastructure for controlling heartbeat and election timeout timers during test execution.

This testing feature enables fine-grained control over Raft timing mechanisms, allowing tests to simulate real-world timing scenarios while maintaining deterministic test execution:

1. **Timer Enabling/Disabling**: Control when timers are active during tests
2. **Selective Timer Control**: Enable timers on specific nodes only
3. **Real-World Timing**: Use actual timer values for realistic testing
4. **Deterministic Testing**: Disable timers for predictable test execution
5. **Transition Control**: Enable timers at specific test phases

**Key Testing Capabilities**:
- Start tests with timers disabled for manual control
- Enable timers to test automatic timeout and heartbeat behavior
- Simulate real-world timing scenarios with actual timeout values
- Test timer-driven elections and leader failure detection
- Control timing across different test phases
- Validate behavior under both manual and automatic timing

**Usage Patterns**:
- Begin with disabled timers for setup and manual operations
- Enable timers when testing automatic behaviors
- Use real timer values to validate production-like scenarios
- Control timing per node for complex partition scenarios

This feature is essential for testing both the manual control aspects of Raft (for debugging) and the automatic timing behaviors (for production scenarios).