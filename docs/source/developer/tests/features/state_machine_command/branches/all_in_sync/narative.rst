followers are replicating the leader's log records as soon as they come in, no network problems are
causing delays, no overloading is causing any node to get behind. This should result in
the minimum number of messages to complete the replication, and append entries from the leader
to each follower, and an append entries reply from each follower to acknowledge that the record
has been saved.

It most of the tests there is also a follow-on heartbeat message, an append entries message with
no log record to add. This is done because followers will not commit and apply the log record
until the leader sends an append entries message containing a commitIndex value greater than
or equal to the record in question. This would not automatically happen in a real system under
normal operations as the leader would often be sending a new command before the heartbeat timeout
expires. However, most of the tests disable heartbeats, and the test usually wants to test the
log states of the nodes once the command is committed and applied, so the standard command
runner logic in the test support code automatically tells the leader to send a heartbeat
after it applies the command.

