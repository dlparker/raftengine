.. state_machine_command.request_redirect:

State Machine Commands -> request redirect
==========================================

Thesis references
-----------------
* **Log replication**: section 3.5
* **Client Interaction**: section 6

Although the library does not directly implement a communications service for the Raft messages,
it provides some support for the job those services must do. In this example an attempt to
perform a state machine command at a server node that is not the cluster leader via
the HullAPI it will receive a redirect response. This is only true if the node in question
knows the ID of the leader, which will not be true if an election is in progress.



