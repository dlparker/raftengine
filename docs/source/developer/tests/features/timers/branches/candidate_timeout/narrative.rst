This feature branch validates that candidates properly handle election timeouts when they cannot gather sufficient votes, and automatically retry with incremented terms until successful election or network recovery.

**Key Candidate Timeout Behaviors**:

- **Election Timeout Detection**: Candidates detect when election attempts fail to complete within timeout periods
- **Term Increment**: Failed elections result in term advancement and automatic retry
- **Persistence**: Candidates continue attempting elections until successful or network conditions improve
- **Termination**: Candidates stop attempts and become followers when they discover a valid leader

**Liveness Requirements**: Candidate timeout handling ensures that the cluster can eventually elect a leader even under adverse network conditions, maintaining the liveness property of the Raft consensus algorithm.