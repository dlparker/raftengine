This feature category covers the Raft cluster membership change operations described in Section 4.1 of Diego Ongaro's Raft thesis. These operations allow nodes to be added to or removed from the cluster during normal operation without compromising safety or availability.

**Key Membership Change Operations**:

- **Adding Followers**: Integration of new nodes into an existing cluster, including log synchronization and configuration replication
- **Removing Followers**: Safe removal of follower nodes from the cluster with proper configuration updates
- **Removing Leaders**: Coordinated leader removal that triggers re-election while maintaining cluster operation
- **Message Handling**: Proper serialization, validation, and processing of membership change messages
- **Configuration Tracking**: Database operations to track the progress and state of ongoing membership changes

**Safety Properties**:

The implementation ensures that membership changes maintain Raft's safety guarantees through careful coordination of configuration changes, proper handling of votes during transitions, and atomic updates to cluster membership state.

**Integration Points**:

Membership changes interact closely with leader election (for leader removal scenarios), log replication (for configuration propagation), and event handling (for change notifications and callbacks).