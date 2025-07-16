This feature branch validates that a candidate correctly manipulates its current term when it discovers messages from nodes with higher terms during an election process.

When a candidate receives messages with terms higher than its own, it must immediately update its current term to match the higher term and transition to follower state. This ensures that the cluster maintains term monotonicity and prevents split-brain scenarios where multiple leaders could exist.

**Key Validation Points**:

- **Term Update**: Candidate immediately updates its term to match the higher discovered term
- **Role Transition**: Candidate transitions from candidate to follower state
- **Election Termination**: Current election process is abandoned in favor of the higher term
- **State Consistency**: Node state remains consistent with the new term

**Test Scenario**:
During an election, a candidate discovers that other nodes are operating with a higher term. The candidate must immediately update its term and abandon its election campaign to maintain cluster consistency and prevent election conflicts.