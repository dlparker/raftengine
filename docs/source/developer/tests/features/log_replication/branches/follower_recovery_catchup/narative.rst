When a follower node recovers from a crash or network partition, it needs to catch up with the leader's log to maintain consistency. This process involves the leader sending AppendEntries messages to the recovered follower, starting from the point where the follower's log diverged from the leader's log.

The catch-up process ensures that:
1. The follower's log is brought up to date with the leader's committed entries
2. Any conflicting entries in the follower's log are overwritten with the leader's entries
3. The follower's commit index is updated to reflect the leader's committed entries

This mechanism maintains the Log Matching property described in Diego Ongaro's thesis Section 3.5, ensuring that all nodes eventually converge to the same log state.