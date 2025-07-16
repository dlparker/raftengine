This feature branch validates leader election behavior when the PreVote optimization is explicitly disabled, forcing the system to use the core Raft election algorithm without the preliminary voting phase.

The PreVote optimization was introduced to reduce unnecessary term increments and network traffic during elections by performing a preliminary voting round before the actual election. However, many test scenarios require the simpler, more predictable behavior of the original Raft election algorithm where candidates immediately increment their term and request votes.

**Key Validation Points**:

- **Direct Term Increment**: Candidates immediately increment term when starting election
- **Immediate Vote Requests**: No preliminary voting phase before real vote requests
- **Simpler State Transitions**: Fewer intermediate states during election process
- **Test Controllability**: More predictable timing and message patterns for testing
- **Core Algorithm Focus**: Tests fundamental Raft election logic without optimizations

**Election Process Without PreVote**:
1. Follower detects leader timeout or receives start_campaign trigger
2. Node immediately transitions to Candidate role
3. Candidate increments its current term by 1
4. Candidate votes for itself in the new term
5. Candidate sends RequestVote messages to all other cluster members
6. Followers respond with vote grants or denials based on standard Raft rules
7. Candidate becomes leader if it receives majority of votes
8. If election fails, candidate may timeout and start new election

**Behavioral Differences**:
- **Term Consumption**: Each election attempt consumes a term number even if unsuccessful
- **Split Vote Frequency**: Higher likelihood of split votes requiring multiple election rounds
- **Network Overhead**: More RequestVote messages sent across the network
- **Timing Sensitivity**: Election outcomes more dependent on message delivery timing

**Testing Benefits**:
Using elections without PreVote provides several advantages for test implementation:
- **Deterministic Behavior**: Fewer edge cases and state transitions to consider
- **Message Flow Simplicity**: Direct RequestVote/RequestVoteResponse pattern
- **Timing Predictability**: More straightforward message sequencing
- **Error Scenario Setup**: Easier to create specific election failure conditions

This mode is particularly valuable for tests that need precise control over election timing and message delivery, allowing test scenarios to focus on core Raft consensus logic without the complexity introduced by optimization layers.