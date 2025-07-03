Heartbeat messages are empty AppendEntries messages (containing no log entries) that the leader sends periodically to maintain its authority and prevent followers from starting new elections. These messages serve several critical purposes:

1. **Leader Authority**: Proves to followers that the leader is still active and functioning
2. **Election Prevention**: Resets follower election timers, preventing unnecessary elections
3. **Commit Index Updates**: Notifies followers of advances in the leader's commit index
4. **Network Connectivity**: Maintains communication channels between leader and followers

Heartbeats are essential for cluster stability and are sent at regular intervals (typically much more frequently than the election timeout) as described in Diego Ongaro's thesis Section 3.5. They ensure that a stable leader remains in power and that followers stay synchronized with committed entries.