This feature branch validates that a candidate properly detects and responds to messages containing higher terms than its current election term, ensuring proper term advancement in the cluster.

The Raft protocol requires that any node receiving a message with a higher term must immediately update to that term and convert to follower state. For candidates, this means abandoning their current election campaign and acknowledging the authority of the higher term.

**Key Validation Points**:

- **Term Detection**: Candidate correctly identifies messages with higher terms
- **Immediate Response**: Candidate responds immediately to higher term discovery
- **Protocol Compliance**: Follows Raft rules for term advancement
- **Election Abandonment**: Stops current election when higher term is discovered

**Test Scenario**:
A candidate in the middle of an election receives a message from another node operating at a higher term. The candidate must detect this higher term, update its own term, and abandon its election campaign to maintain cluster consistency.