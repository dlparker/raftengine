:orphan:

This is the central feature of the Raft algorithm. The election process guarantees that there is only one leader
node in a cluster, and that it has all the log records that are committed in the cluster. That allows it to
replicated new log entries using the commit protocl defined in the thesis.

I found it a bit difficult to work out one detail, so it is explicitly noted here. Once
the leader receives a sufficient number of replies to the append entry messages for a given log record, it
commits the record locally. Only after that does it apply the record to the state machine, assuming it is
a state machine command.

This was a bit mind bending to me until I got used to the idea, as I
am so trained to think of commits as being the final stage of
**applying** a change to persistence. They still are in this case, but
only with respect to the Raft log. If the application's state machine
is persistent, then the change in persistent state occurs **after**
the commit.

This means the node must persist both the commit index and the applied index so that it
can apply the last committed record should it happen to crash after commit but before apply. This
is mentioned in section 3.8, but it is not clear to me from that text whether the Raft logic
or the application state machine logic is responsible for persisting the applied index. I chose
to have the Raft logic do it. This is updated after the state machine command is executed, implying
that the new state has been persisted if needed.

There is a similar wrinkle involving followers: they only commit the record when they see that the leader
has already committed the record, and afterwords they apply it. 

