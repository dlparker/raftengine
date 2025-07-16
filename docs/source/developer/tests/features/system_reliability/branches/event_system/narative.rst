Event System provides comprehensive monitoring and notification capabilities for Raft operations, enabling observability and debugging of distributed consensus processes.

This feature validates the event-driven monitoring infrastructure that tracks role changes, term updates, leader transitions, election operations, and log synchronization activities:

1. **Role Change Events**: Monitor transitions between FOLLOWER, CANDIDATE, and LEADER states
2. **Term Change Events**: Track term progression across cluster nodes
3. **Leader Change Events**: Detect leadership transfers and new leader establishment
4. **Election Operation Events**: Monitor detailed election phases and outcomes
5. **Resync Operation Events**: Track log synchronization and catchup operations

**Key Validation Points**:
- Events are generated correctly for all major state transitions
- Event handlers receive proper event notifications with accurate data
- Event serialization (to_json) works correctly for debugging
- Multiple event handlers can be registered and managed
- Event handlers can be added and removed dynamically
- Events provide sufficient detail for system monitoring and debugging

**Event Types Monitored**:
- Role changes during elections and step-down operations
- Term updates when nodes learn about newer terms
- Leadership establishment and changes
- Election progress through various phases
- Log resynchronization operations and catchup procedures

This feature is essential for system observability, debugging distributed consensus issues, and enabling sophisticated monitoring of Raft cluster health and operations.