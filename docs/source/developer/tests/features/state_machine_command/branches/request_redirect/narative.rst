perform a state machine command at a server node that is not the cluster leader via
the DeckAPI it will receive a redirect response. This is only true if the node in question
knows the ID of the leader, which will not be true if an election is in progress.

