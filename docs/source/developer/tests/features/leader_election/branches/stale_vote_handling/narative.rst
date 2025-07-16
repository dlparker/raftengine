This feature branch validates that a candidate correctly processes and handles vote responses that arrive after the candidate has already discovered higher terms and resigned from its election.

When a candidate resigns due to higher term discovery, there may still be pending vote responses from its original election request. The candidate must properly handle these stale responses without affecting its new follower state or causing confusion in the election process.

**Key Validation Points**:

- **Stale Response Detection**: Candidate identifies vote responses from previous terms
- **Response Filtering**: Stale votes are ignored and don't affect current state
- **State Preservation**: Follower state is maintained despite receiving old votes
- **Election Isolation**: Previous election results don't interfere with current cluster state

**Test Scenario**:
A candidate starts an election, then discovers a higher term and resigns. Vote responses from its original election arrive after resignation. The candidate must properly ignore these stale responses while maintaining its follower state.