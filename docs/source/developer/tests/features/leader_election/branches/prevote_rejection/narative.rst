This feature branch validates the system's ability to reject pre-vote requests when a stable leader already exists, preventing unnecessary elections and term disruptions in healthy clusters with active leadership.

Pre-vote rejection is a critical safety mechanism that prevents nodes from disrupting stable leadership when they inappropriately attempt to start elections. When a leader is actively sending heartbeats and the cluster is healthy, other nodes should reject pre-vote requests to maintain stability.

**Key Validation Points**:

- **Leadership Recognition**: Nodes recognize when valid leader exists
- **Pre-Vote Rejection**: Followers reject pre-vote requests during stable leadership
- **Heartbeat Correlation**: Recent heartbeats indicate leader health and authority
- **Campaign Prevention**: Rejected pre-votes prevent unnecessary election attempts
- **Cluster Stability**: Rejection mechanism maintains existing leadership
- **Term Protection**: Prevents spurious term increments from failed elections

**Pre-Vote Rejection Process**:
1. Cluster operates normally with established leader sending heartbeats
2. Follower receives recent heartbeat from current leader
3. Different node attempts to start election by sending pre-vote requests
4. Recipients check for recent leader activity (heartbeats)
5. If leader is active, recipients reject pre-vote with negative response
6. Requesting node receives majority of rejections
7. Election attempt is abandoned, existing leader remains in power
8. Cluster continues normal operation without disruption

**Rejection Criteria**:
- **Recent Heartbeat**: Leader heartbeat received within timeout window
- **Term Currency**: Current leader's term is up-to-date
- **Leader Authority**: Leader demonstrates active cluster management
- **Timing Thresholds**: Heartbeat recency within configured timeout limits
- **Majority Rejection**: Sufficient rejections to prevent election

**Leadership Stability**:
- **Active Leader**: Functioning leader prevents election attempts
- **Heartbeat Authority**: Regular heartbeats establish leader legitimacy
- **Spurious Prevention**: Rejects inappropriate election attempts
- **Term Preservation**: Prevents unnecessary term advancement
- **Cluster Health**: Maintains stable operation during leader health

**Implementation Testing**:
This feature tests the essential stability mechanism that prevents healthy clusters from experiencing unnecessary leadership changes, ensuring that established leaders can maintain authority as long as they demonstrate active cluster management through regular heartbeats.