
# Raft Based Server Library

This code began life as a fork of
[baonguyen2604/raft-consensus](https://github.com/baonguyen2604/raft-consensus).
The code orignally forked was chosen because it is the most
understandable, straightforward implementation that provided enough of
the raft features, compared to the other python implementations
studied. A key motivator of the raft algorithm is to be sufficiently
understandable that it is likely to be implemented correctly. It seems
reasonable to take as a corollary the goal that the implementation should
also be easy to understand. The chosen fork base did that well.

However, the original code had features that seem to indicate that it
was just a proof of concept, not intended to be production code. This
fork therefore had to make a number of basic changes to eliminate those
features.

Also, it was like many of the other projects I have found in that it was built as
a server with the raft protocol tightly integrated with the server functions. For example,
it assumed that all the RPC activity that the servers would do would be provided
by the raft RPCs. It also assumed that the provided raft log was sufficient for
storing the server application's state.

These assumptions are fine for a demo or study project, but a real
server process is likely to have other communications needs and want
to own the management of the communications operations. Likewise, when
a real server executes the "state machine command", roughly in the
language of the raft paper, it is likely to have more things to store
than just the transported "command". For example, it might need to include
other database operations in the command processing, so providing its own
log to the raft code would make it possible to enclose the raft log records
in a transaction with the other needed updates.

So, eventually it underwent a complete rewrite. The only original elements
remaining are:

1. The structure of the message classes, where the specific messages
   derive from a base class, and the names of the specific messages,
   which in turn derive from the original paper found in raft.pdf.
2. The structure of the state classes, where the specific states
   derive from a base class, and the state names, which in turn
   derive from the original paper found in raft.pdf.
3. The names of the messages and states directories, which are kinda obvious.

As a result, I have changed the license file to include me as copyright
holder, and removed Bao Nguyen's name. 
I am not a lawyer, but I have studdied software copyright litigation,
and my laymen's assessment is that nothing I retained constitutes copying
of the original. 

The main purpose of this project is to make it a generalized library
to aid in the construction of cluster of servers. 

When building a server that is going to be part of a cluster that uses
raft for consensus, then changes in the cluster configuration should trigger
user code in order to allow decisions about possible processing algorithm adjustments.
This project is designed to provide a frame on which to build such servers.

## References

- [raftos](https://github.com/zhebrak/raftos)
- [protocol extensions](https://dev.to/tarantool/raft-notalmighty-how-to-make-it-more-robust-3a11)
- [simpleRaft](https://github.com/streed/simpleRaft/tree/master/simpleRaft)
- [Raft visualization](http://thesecretlivesofdata.com/raft/)
