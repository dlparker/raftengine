This feature branch validates that a candidate in an election properly rejects AppendEntries messages from leaders with lower terms, as required by the Raft consensus algorithm.

When a network partition heals during an election, the old leader (with a lower term) may attempt to send heartbeats to a candidate that has started an election with a higher term. According to Raft protocol, the candidate must reject these AppendEntries messages to maintain safety properties and ensure proper leader election completion.

**Key Validation Points**:

- **Term Comparison**: Candidate correctly compares message term with its current term
- **Message Rejection**: AppendEntries with lower terms are rejected outright
- **Election Continuation**: Candidate continues election process despite receiving old leader messages
- **Safety Preservation**: Prevents old leader from interfering with new leader election

**Test Scenario**:
A leader gets partitioned from followers, then followers start an election with a higher term. When the network heals during the election, the old leader sends heartbeats that the candidate must reject to preserve election integrity.