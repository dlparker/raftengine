This feature category covers Raft log compaction through snapshots as described in Section 7 of Diego Ongaro's Raft thesis. Snapshots enable Raft clusters to manage storage by compacting applied log entries into a single snapshot point, reducing memory usage and enabling efficient catch-up for new or lagging nodes.

**Key Snapshot Operations**:

- **Snapshot Creation**: Creating point-in-time snapshots of the state machine at both leader and follower nodes
- **Log Compaction**: Safely removing applied log entries after snapshot creation while maintaining safety
- **Snapshot Transfer**: Efficiently transferring snapshots between nodes using chunked streaming
- **Snapshot Installation**: Installing received snapshots and updating log state accordingly
- **Leadership with Snapshots**: Leaders operating correctly when their log state is based on snapshots

**Safety Properties**:

Snapshot operations maintain Raft's safety guarantees through careful coordination of snapshot timing, proper handling of concurrent operations during snapshot creation, and atomic installation procedures.

**Performance Benefits**:

Snapshots enable unbounded log growth management, faster node recovery through state transfer rather than log replay, and efficient integration of new cluster members without full log history transfer.