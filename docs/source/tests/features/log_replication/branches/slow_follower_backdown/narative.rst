


log_replication.slow_follower_backdown
--------------------------------------

When a leader sends an append entries message to a follower it includes the index of the last log record and the term
of that record, and the follower compares those values to its own last log record. There are a variety of scenarios
depending on the relationship between these values, but this one concerns the cases where the follower's index
is less than the leader's index, and the actual last record at the follower is present at the same index in the
leader's log.

In this case a series of one or more append entries messages from the leader will occur where each time one is sent
the index of the record decreases by one. This is described in section 3.5 where it refers to the **nextIndex** value
that the leader maintains for each follower. In this library these are referred to as "backdown" messages.

In this scenario the log index and log record term will eventually match. If that happens on the first backdown message,
which will be true if the follower is exactly one log record behind, then the follower will save the log record and
will be current to that point. If this sequence began with a heartbeat message, that means that the follower is up to date.
This is the simplest of the slow follower backdown scenaios.

If the sequence because because with a append entries message that included one or more new log record,
then the leader will switch to the process that this library calls "catchup" messages, sending entries until
the final log record in the follower's log matches the final log record in the leader's log.
