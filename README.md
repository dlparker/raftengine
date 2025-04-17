# Raft Based Server Library

The main purpose of this project is to make it a generalized library
to aid in the construction of cluster of servers by supplying
Raft consensus as a service to application servers.

The target user is the developer of a distrubuted system that performs
functions that are not mediated by the Raft operations, but where
such operations can help solve the thorny problems of cluster management.

For example, a cluster might not be symetrical with respect to a given
client request. A log streaming cluster might want to direct client
requests based on the topic of interest, and only some of the servers
in the cluster manage that topic. Any time you want to change the
association of specific servers with specific topics, you find yourself
dealing with the tricky problem that Raft is meant to solve.

If the user is building their own distributed system cluster and doing
things that are not to be mediated by Raft, then they the system
almost certainly has some form of server to server communication, via
RPCs, message passing, something. They typically also have some
requirements for managing persistent storage that is outside the Raft
Log needs.

Therefore, this library in its primary form provides neither transport
nor storage directly, rather it defines elements of the API to
accept and use services provided by the user.

An optional part of the library provides implementations of these
services for the user to use, or to modify and use. These are
referred to as transport and log "assists".

Demos are provided to do from scratch implementations and modified
assists.


- [protocol extensions](https://dev.to/tarantool/raft-notalmighty-how-to-make-it-more-robust-3a11)
