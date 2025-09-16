This feature branch validates the safe removal of follower nodes from a Raft cluster. The process involves the follower node initiating its own removal and the leader coordinating the cluster configuration update.

**Key Operations**:

- Follower requests its own removal via `exit_cluster()` call
- Leader processes the removal request and updates cluster configuration
- Event handlers notify of membership change completion or failure
- Removed node stops participating in cluster operations
- Heartbeat patterns adjust to exclude the removed node

**Safety Guarantees**: The removal process ensures that the remaining cluster maintains quorum and continues normal operations. The removed node cleanly shuts down its Raft role and stops processing messages.