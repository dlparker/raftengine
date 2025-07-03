
Network partitions are a fundamental challenge that Raft is designed to handle gracefully.
The algorithm ensures that during a partition, at most one partition can make progress
(the one containing a majority of nodes), while minority partitions remain blocked.

**Raft Thesis Reference**: Section 3.2 (Safety Properties), Section 3.4 (Leader Election)

Raft's approach to network partitions relies on the majority quorum requirement:

1. **Majority Partition**: Can elect leaders and commit log entries
2. **Minority Partition**: Cannot achieve quorum, remains read-only
3. **Partition Recovery**: When network heals, minority accepts majority's state

The safety properties ensure that:
- **Election Safety**: At most one leader per term across all partitions
- **Log Matching**: Consistent log state when partitions reunite
- **Leader Completeness**: New leaders contain all committed entries

Key mechanisms:
- **Quorum Requirements**: Prevents split-brain scenarios
- **Term Numbers**: Ensures proper leader succession during partition recovery
- **Log Consistency Checks**: Maintains data integrity across partition boundaries

This feature category encompasses various partition scenarios including leader isolation,
follower isolation, symmetric partitions, and partition recovery patterns.