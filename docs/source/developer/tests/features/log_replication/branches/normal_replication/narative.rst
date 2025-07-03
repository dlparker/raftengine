The normal log replication process is the core mechanism by which a Raft leader maintains consistency across the cluster. When the leader receives a client command, it:

1. Appends the command as a new log entry with the current term
2. Sends AppendEntries messages to all followers containing the new entry
3. Waits for a majority of followers to acknowledge receipt (AppendResponse)
4. Once a majority responds successfully, marks the entry as committed
5. Applies the committed entry to the state machine
6. Notifies followers of the new commit index via subsequent AppendEntries

This process implements the Log Replication protocol described in Diego Ongaro's thesis Section 3.5, ensuring that committed entries are durably stored and consistently ordered across all nodes in the cluster.