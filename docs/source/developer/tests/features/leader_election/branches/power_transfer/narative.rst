Power Transfer tests the orderly transfer of leadership from one node to another without waiting for timeout-based elections.

This feature validates the leadership transfer mechanism that allows a current leader to voluntarily step down and designate a specific successor. The process ensures minimal cluster disruption during planned leadership changes:

1. **Transfer Initiation**: Current leader identifies target node and initiates transfer process
2. **Target Preparation**: Target node receives transfer notification and prepares for leadership
3. **Voluntary Step Down**: Current leader stops accepting new commands and steps down
4. **Successor Election**: Target node initiates election process to become new leader
5. **Leadership Transition**: Cluster recognizes new leader and resumes normal operations

**Key Validation Points**:
- Transfer process completes successfully with healthy target nodes
- Current leader properly stops accepting commands during transfer
- Target node successfully wins election and assumes leadership
- Cluster maintains availability throughout the transfer process
- All nodes recognize the new leader after transfer completion

This feature is essential for planned maintenance operations, load balancing, and cluster administration tasks that require controlled leadership changes.