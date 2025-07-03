
This feature branch covers the scenario where a leader that has been isolated by a network 
partition rejoins the network after a new leader has been elected in its absence.

**Raft Thesis Reference**: Section 3.4 (Leader Election), Section 3.2 (Safety Properties)

When a leader becomes isolated from the majority of the cluster due to network partition,
the remaining nodes will eventually timeout and start a new election. During this time,
the isolated leader continues to believe it is the leader but cannot replicate log entries
since it lacks a quorum.

Upon network recovery, the isolated leader must discover that a new leader has been elected
with a higher term. This discovery happens when:

1. The old leader receives a message with a higher term number
2. The old leader attempts to send a message and receives a rejection due to stale term
3. The old leader receives an AppendEntries message from the new leader

The safety properties of Raft ensure that:
- The old leader will immediately step down when it discovers the higher term
- Any uncommitted log entries from the old leader's partition period will be discarded
- The cluster converges to the state maintained by the new leader

This behavior is critical for maintaining the "at most one leader per term" safety property
and ensuring that split-brain scenarios are properly resolved.