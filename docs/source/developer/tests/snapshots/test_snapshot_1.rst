.. _test_snapshot_1:

=============================================
Test test_snapshot_1 from file test_snapshots
=============================================


    Tests the mechanisms in the dev_tools test support code that implement snapshot operations.
    Doesn't do any snapshot work with the raft operations, just establishes that the "state machine"
    snapshot creation and use works.

    No raft operations are run, so the traces will contain only the node start trace.
    

