The current directory contains the start of a demo app that I am building for a raft library.
The goal for this demo is to serve as a guide to demonstrate how to take a working application
and add raft consensus support via the library. The parent directory contains that library, but
at the moment it should be ignored as it will not help complete the current tasks.

The demo app is (mostly) a client server system that does a bunch of simulated banking operations.
The basic elements of the app are found in src/base.

The "no_raft" version of the app system includes a "direct" mode version which is not a client/server app,
it just performs the functions with direct in process calls from the client logic to the server logic.
This is meant to make it easy for readers to understand what functions are performed by the more
complex versions of the app system.

There are three forms of the app system, with varying status. The current focus of
development is finishing the second form to the same level as the first form.


1. No Raft - meant to let the reader think about standard client server techniques
   1. Pretty well finished
   2. found in src/no_raft
   3. Includes two RPC mechanisms, GRPC and an asyncio streams based implementation

2. Raft Prep - meant to show how to build the RPC support needed for adding the Raftengine library
   1. Only completed for asyncio streams base RPC
   2. found in src/raft_prep
   3. Uses stub files to implement methods that would connect the application server core to the
      transport mechanism, with a little sim logic to make it work end to end.

3. Raft - raftengine library integrated
   1. Not at all done
   2. Will be in src/raft
   3. Not the focus of this phase of development.






The first phase is to get a simple banking simulation working with pattern found in these files, where the client
has a proxy object that it calls to get the banking operation, the proxy converts the method call
to a serializable name of the operation and its arguments, then submits it the a server wrapper object.
This is intended to be anologous to converting a client request to a "state machine command" and replicating it
in the raft log. The server wrapper object converts it to a method call on the actual server method.


The server code is the most complete part of the skeleton. One method "create_customer" has been implemented in all four classes and functions, as shown in t.py. 
