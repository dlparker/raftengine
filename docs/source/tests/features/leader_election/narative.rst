:orphan:

The main elements of leader election are defined in section 3.4 of the thesis. There
are many legal sequences of interaction between nodes in the cluster that can
lead to a leader being elected. These are covered in the various feature branch
descriptions.

The thesis is a later version of the original paper, and it includes some improvements
to address stability issues. Some of these were not woven into the original texts but
added in later additional sections of the updated document. Section 6.4.1 deals with
the reasoning behind a log record addition at the end of a successful election and how
it helps in certain situations. The thesis says that this is a "blank no-op" record, but
this library calls it a "TERM_START" record. The effect of this record on the Raft
algorithm is identical regardless of what you call it. This library also uses that record
to record the state of the cluster configuration at the start of the term. This has
the side effect of making it possible for a crashed server to recover this state, even
if the log was destroyed in the crash as the TERM_START log record will be replayed.


In the majority of the tests the timeout mechanisms are circumvented by assigning
long values to the heartbeat and election timers so that tests can complete without
timers firing. The events that would normally be caused by these timers, such as starting
an election, sending a heartbeat, etc. are forcibily triggered by direct calls from the test code to the
corresponding library functions. Here is a typical examples:

.. code-block:: python
		
    # cause the test server node 1 to switch to candidate role and ask for votes
    await ts_1.start_campaign()


    # cause the test server node 1 (which is the leader) to send heartbeat messages
    await ts_1.send_heartbeats()
    
