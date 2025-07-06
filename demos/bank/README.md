The current directory contains the start of a demo app that I am building for a raft library.
The first phase is to get a simple banking simulation working with pattern found in these files, where the client
has a proxy object that it calls to get the banking operation, the proxy converts the method call
to a serializable name of the operation and its arguments, then submits it the a server wrapper object.
This is intended to be anologous to converting a client request to a "state machine command" and replicating it
in the raft log. The server wrapper object converts it to a method call on the actual server method.


The server code is the most complete part of the skeleton. One method "create_customer" has been implemented in all four classes and functions, as shown in t.py. 
