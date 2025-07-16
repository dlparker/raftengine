This feature branch validates that a candidate can properly detect when its current term is outdated compared to the cluster's current term, preventing stale candidates from disrupting ongoing elections.

When a candidate has been partitioned or delayed, other nodes may have already advanced to higher terms. The candidate must detect this situation and update its term appropriately rather than attempting to run an election with an outdated term.

**Key Validation Points**:

- **Term Currency Check**: Candidate evaluates whether its term is current
- **Response Analysis**: Vote responses reveal current cluster term state
- **Automatic Update**: Candidate updates to discovered higher terms
- **Election Abortion**: Outdated election attempts are abandoned

**Test Scenario**:
A candidate attempts to start an election with an outdated term. When it receives responses indicating higher terms exist in the cluster, it must detect this situation, update its term, and abandon its election attempt.