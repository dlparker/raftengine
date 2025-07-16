This feature branch enables precise, step-by-step control over the leader election process, allowing tests to manually trigger and validate each phase of the election algorithm with fine-grained control over timing and message delivery.

Manual stepwise control is essential for comprehensive testing of Raft election behavior, enabling test scenarios that would be difficult or impossible to achieve with fully automated election processes. This approach allows tests to pause execution at specific points, examine intermediate states, and control the progression of the election.

**Key Control Capabilities**:

- **Campaign Initiation**: Manual triggering of candidate election start
- **Message Flow Control**: Step-by-step control over vote request and response delivery
- **State Validation**: Ability to examine node states between election steps
- **Timing Control**: Precise control over when each election phase occurs
- **Error Injection**: Controlled introduction of failures at specific election points

**Stepwise Election Control Process**:
1. **Manual Campaign Start**: Test explicitly calls `start_campaign()` on target node
2. **Message Generation Control**: Control when RequestVote messages are created and queued
3. **Message Delivery Control**: Manual control over when messages are sent to network
4. **Response Handling Control**: Step-by-step processing of incoming vote responses
5. **State Transition Control**: Manual triggering of role transitions (Candidate to Leader)
6. **Validation Points**: Examination of node state after each controlled step

**Testing Infrastructure Integration**:
- **Trigger-Based Execution**: Uses trigger system to pause and resume execution
- **Message Queue Control**: Manual management of input and output message queues
- **Timer Disabling**: Election timeouts disabled to prevent automatic progression
- **Network Simulation**: Controlled message delivery through simulated network layer

**Granular Control Points**:
- **Vote Request Generation**: When candidates create RequestVote messages
- **Vote Request Transmission**: When vote requests are sent to followers
- **Vote Processing**: When followers process incoming vote requests
- **Vote Response Generation**: When followers create and send vote responses
- **Vote Response Reception**: When candidates receive and process vote responses
- **Leader Election**: When candidate with majority votes becomes leader
- **Term Start Entry**: When new leader creates and replicates term start entry

**Validation Capabilities**:
Between each step, tests can validate:
- **Node Role States**: Verify correct role transitions (Follower → Candidate → Leader)
- **Term Values**: Confirm proper term increments and consistency
- **Vote Tracking**: Check voted_for values and vote counting
- **Message Contents**: Examine message fields and parameters
- **Log States**: Verify log consistency and term start entry creation

**Error Scenario Testing**:
Manual control enables testing of complex failure scenarios:
- **Split Vote Conditions**: Control vote distribution to create split votes
- **Message Loss**: Selectively drop messages at specific points
- **Timing Conflicts**: Create race conditions between candidates
- **Network Partitions**: Control message delivery to simulate partitions

This feature is particularly valuable for regression testing and debugging election edge cases, providing the precision needed to reproduce specific election behaviors and validate the correctness of the Raft election implementation under controlled conditions.