This feature validates one of Raft's most critical safety properties: the guarantee that each follower votes for at most one candidate in any given term. This property is essential for preventing multiple leaders from being elected simultaneously and maintaining cluster safety.

The single-vote-per-term constraint serves as a fundamental building block of Raft's safety guarantees, ensuring that leadership elections maintain consensus even under challenging network conditions or competing candidates.

**Core Safety Mechanism**:

The single vote per term rule operates through several key mechanisms:

- **Vote Tracking**: Each node maintains a record of its vote for the current term
- **Vote Rejection**: Once a vote is cast, all subsequent RequestVote messages for the same term are rejected
- **Term Advancement**: Voting state is reset only when advancing to a new term
- **Persistent Storage**: Vote decisions must survive node restarts to maintain safety

**Protocol Implementation**:

**Vote Decision Logic**:
1. Check if already voted in current term
2. If not voted, evaluate candidate qualifications (log completeness)
3. If qualified, grant vote and record decision persistently
4. If already voted, reject request regardless of candidate qualifications

**Rejection Response**:
- Return `voteGranted: false` in RequestVoteResponse
- Include current term to help candidate detect stale terms
- Maintain existing vote record without modification

**State Management**:
- `votedFor` field tracks vote recipient for current term
- Reset to null only when entering new term
- Must be persisted to stable storage before responding to vote requests

**Safety Implications**:

**Prevention of Split Leadership**:
- Multiple candidates cannot each receive majority votes in same term
- At most one candidate can receive n/2+1 votes from n nodes
- Eliminates possibility of multiple leaders claiming legitimacy

**Consistency Guarantees**:
- Ensures deterministic election outcomes given same starting conditions
- Prevents byzantine failures from corrupting election process
- Maintains linearizability of leadership transitions

**Recovery Properties**:
- Vote decisions survive node crashes and restarts
- Prevents vote change after recovery in same term
- Maintains election integrity across failures

**Testing Validation**:

**Primary Test Scenarios**:
1. **Initial Vote Grant**: Verify first RequestVote in term receives positive response
2. **Subsequent Vote Rejection**: Verify additional RequestVote messages are rejected
3. **Cross-Term Behavior**: Verify vote state resets when advancing to new term
4. **Persistence Validation**: Verify vote decisions survive simulated node restarts

**Edge Case Coverage**:
- Simultaneous vote requests from different candidates
- Vote requests received during term transitions
- Recovery scenarios with partially committed vote state
- Network partition scenarios affecting vote distribution

**Integration with Other Properties**:

The single-vote-per-term property works in conjunction with other Raft safety mechanisms:

**Log Matching Property**: Prevents less qualified candidates from receiving votes even if they request first

**Leader Completeness**: Ensures only candidates with complete logs can win elections

**Term Monotonicity**: Prevents regression to earlier terms with different vote outcomes

**Election Safety**: Guarantees at most one leader per term across entire cluster

This feature is fundamental to Raft's correctness and must be rigorously validated through comprehensive testing that covers all possible election scenarios and failure conditions.