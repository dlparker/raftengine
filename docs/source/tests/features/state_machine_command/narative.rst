.. state_machine_command:

State Machine Commands
======================


The term "state machine" in the Raft thesis probably requires a somewhat liberal interpretation. In terms
of how the Raft algorithm views the "application" that is the focus of all this activity, that is correct.
However, it may be that much application logic lies beyond the "state machine" part of the program. So,
probably, the authors of the application need to think about inputs and outputs to whatever they are doing
working as a "state machine". So maybe the state changes is that a new request for work has been queued,
not necessarily that the actual work has been completed.

Anywho, the language in the thesis talks about a "command" having been applied to the "state machine",
so that is the terminology and logic that this library uses.

The tests mostly use a stupidly simple state machine implementation with is just an integer value that
commands can increment or decrement. It does not persist its state. It can be seen in the
dev_tools/operations.py code, in the SimpleOps class.

A slightly more complex "operations" class DictTotalsOps can be found in the same file. It has enough
additionl complexity to be useful for testing log snapshot operations.

The important thing is that many of the details of client interaction described in section 6 of the thesis
do not apply to this library, because it does not provide an RPC or messaging mechanism itself, it needs
to have that service provided through the PilotAPI and HullAPI classes. There are some features of the
library that can help with implementing the section 6 features.

Command Execution
-----------------

When a client wants a state machine command to be executed by the cluster, the server application it is talking
to should submit that request to the HullAPI run_command method. If the server is the cluster leader, then
the normal command sequence begins. It is:

1. Persist the command as a log record at the leader
2. Replicate the log record to the cluster.
3. When a majority of nodes agree, commit the log record at the leader
4. Pass the command to the state machine part of the application server via the PilotAPI process_command
   method and collect the result.
5. Return the command result to the application server as the result of the run_command method.

There are many tests for this logic.

If the leader experiences an error trying to apply the command when calling "process_command" then it
will return an error to the caller. There are tests for this logic.

If the client makes this request at a server that is not the leader, then the run_command method will
immediately return a "redirect" response with the ID of the server, so the application server can handle
it either by proxying it to the leader or returning a redirect response to the client. There are tests for this logic.

If the non-leader server doesn't know who the leader is, which is the case if an election is in progress,
the run_command method will return a "try again" response. There are tests for this logic.

If something goes wrong in the process, the run_command may timeout and return a timeout response.
There are tests for this logic.

Note that there may be pathological failure modes if the state machine logic repeatedly fails to allow
a command to be applied at a follower node, such that it never gets applied. The library does not detect
this scenario so it doesn't try to take corrective action. State machines should detect the condition
and stop the server and call for help. There are no tests for this.


   
   
   
