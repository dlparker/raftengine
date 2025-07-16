This feature branch validates that a candidate properly resigns from its election campaign when it encounters evidence of higher terms in the cluster, preventing election conflicts and maintaining cluster safety.

When a candidate discovers that other nodes are operating with higher terms, it must immediately resign from its current election and transition to follower state. This resignation process ensures that only the highest term election can proceed, preventing split-brain scenarios.

**Key Validation Points**:

- **Resignation Trigger**: Candidate resigns immediately upon discovering higher terms
- **Election Abandonment**: Current election campaign is completely abandoned
- **State Transition**: Candidate transitions to follower state
- **Vote Retraction**: Any pending vote requests are effectively cancelled

**Test Scenario**:
During an active election campaign, a candidate receives evidence that other nodes are operating at a higher term. The candidate must immediately resign from its election, update its term, and become a follower to maintain cluster consistency.