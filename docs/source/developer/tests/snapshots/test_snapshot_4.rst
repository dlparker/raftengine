.. _test_snapshot_4:

=============================================
Test test_snapshot_4 from file test_snapshots
=============================================


    Tests that a node that is "slow" will get a snapshot installed when it falls behind
    a leader that has a snapshot that extends beyond the slow node's log index.
    It uses the dev_tools SqliteLog instead of the usual MemoryLog to ensure that nothing
    about the snapshot operations fails after restart.

    The process is to run an election, crash node 3, run another command so that node 1 (leader)
    and node 2 are both ahead on log index. Next a snapshot is created at node 2, and then an
    election is held to force node 2 to be leader. Next node 3 is restarted, and the details
    of log values are checked to make sure that node 3 installed the snapshot before catching
    up normally.
    
    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    
    

Section 2: Running election to elect node 1
===========================================



.. collapse:: section 2 trace table (click to toggle view)

   - See :ref:`Trace Table Legend` for help interpreting table contents

   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | N-1  | N-1                         | N-1       | N-2  | N-2                         | N-2       | N-3  | N-3                         | N-3       |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | Role | Op                          | Delta     | Role | Op                          | Delta     | Role | Op                          | Delta     |
   +======+=============================+===========+======+=============================+===========+======+=============================+===========+
   | CNDI | NEW ROLE                    |           | FLWR |                             |           | FLWR |                             |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | CNDI | poll+N-2 t-1 li-0 lt-1      |           | FLWR |                             |           | FLWR |                             |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | CNDI | poll+N-3 t-1 li-0 lt-1      |           | FLWR |                             |           | FLWR |                             |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | CNDI |                             |           | FLWR | N-1+poll t-1 li-0 lt-1      | t-1       | FLWR |                             |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | CNDI |                             |           | FLWR | vote+N-1 yes-True           |           | FLWR |                             |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | CNDI |                             |           | FLWR |                             |           | FLWR | N-1+poll t-1 li-0 lt-1      | t-1       |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | CNDI |                             |           | FLWR |                             |           | FLWR | vote+N-1 yes-True           |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | LEAD | N-2+vote yes-True           | lt-1 li-1 | FLWR |                             |           | FLWR |                             |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | LEAD | NEW ROLE                    |           | FLWR |                             |           | FLWR |                             |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | LEAD | ae+N-2 t-1 i-0 lt-0 e-1 c-0 |           | FLWR |                             |           | FLWR |                             |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | LEAD | ae+N-3 t-1 i-0 lt-0 e-1 c-0 |           | FLWR |                             |           | FLWR |                             |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | LEAD | N-3+vote yes-True           |           | FLWR |                             |           | FLWR |                             |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | LEAD |                             |           | FLWR | N-1+ae t-1 i-0 lt-0 e-1 c-0 | lt-1 li-1 | FLWR |                             |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | LEAD |                             |           | FLWR | N-2+ae_reply ok-True mi-1   |           | FLWR |                             |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | LEAD |                             |           | FLWR |                             |           | FLWR | N-1+ae t-1 i-0 lt-0 e-1 c-0 | lt-1 li-1 |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | LEAD |                             |           | FLWR |                             |           | FLWR | N-3+ae_reply ok-True mi-1   |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | LEAD | N-2+ae_reply ok-True mi-1   | ci-1      | FLWR |                             |           | FLWR |                             |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | LEAD | N-3+ae_reply ok-True mi-1   |           | FLWR |                             |           | FLWR |                             |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | LEAD | ae+N-2 t-1 i-1 lt-1 e-0 c-1 |           | FLWR |                             |           | FLWR |                             |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | LEAD |                             |           | FLWR | N-1+ae t-1 i-1 lt-1 e-0 c-1 | ci-1      | FLWR |                             |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | LEAD |                             |           | FLWR | N-2+ae_reply ok-True mi-1   |           | FLWR |                             |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | LEAD | N-2+ae_reply ok-True mi-1   |           | FLWR |                             |           | FLWR |                             |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | LEAD | ae+N-3 t-1 i-1 lt-1 e-0 c-1 |           | FLWR |                             |           | FLWR |                             |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | LEAD |                             |           | FLWR |                             |           | FLWR | N-1+ae t-1 i-1 lt-1 e-0 c-1 | ci-1      |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | LEAD |                             |           | FLWR |                             |           | FLWR | N-3+ae_reply ok-True mi-1   |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | LEAD | N-3+ae_reply ok-True mi-1   |           | FLWR |                             |           | FLWR |                             |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+



.. collapse:: trace sequence diagram (click to toggle view)

   .. plantuml:: /developer/tests/diagrams/test_snapshots/test_snapshot_4_2.puml
          :scale: 100%


Section 3: Node 1 is leader, runing commands 
=============================================



.. collapse:: section 3 trace table (click to toggle view)

   - See :ref:`Trace Table Legend` for help interpreting table contents

   +------+-----+-------+------+-----+-------+------+-----+-------+
   | N-1  | N-1 | N-1   | N-2  | N-2 | N-2   | N-3  | N-3 | N-3   |
   +------+-----+-------+------+-----+-------+------+-----+-------+
   | Role | Op  | Delta | Role | Op  | Delta | Role | Op  | Delta |
   +------+-----+-------+------+-----+-------+------+-----+-------+



.. collapse:: trace sequence diagram (click to toggle view)

   .. plantuml:: /developer/tests/diagrams/test_snapshots/test_snapshot_4_3.puml
          :scale: 100%


Section 4: Crashing node 3, running a command, then taking snapshot at node 2
=============================================================================



.. collapse:: section 4 trace table (click to toggle view)

   - See :ref:`Trace Table Legend` for help interpreting table contents

   +------+-----+-------+------+-----+-------+------+-----+-------+
   | N-1  | N-1 | N-1   | N-2  | N-2 | N-2   | N-3  | N-3 | N-3   |
   +------+-----+-------+------+-----+-------+------+-----+-------+
   | Role | Op  | Delta | Role | Op  | Delta | Role | Op  | Delta |
   +------+-----+-------+------+-----+-------+------+-----+-------+



.. collapse:: trace sequence diagram (click to toggle view)

   .. plantuml:: /developer/tests/diagrams/test_snapshots/test_snapshot_4_4.puml
          :scale: 100%


Section 5: Node 2 has snapshot and empty log, switching it to leader
====================================================================



.. collapse:: section 5 trace table (click to toggle view)

   - See :ref:`Trace Table Legend` for help interpreting table contents

   +------+-----+-------+------+-----+-------+------+-----+-------+
   | N-1  | N-1 | N-1   | N-2  | N-2 | N-2   | N-3  | N-3 | N-3   |
   +------+-----+-------+------+-----+-------+------+-----+-------+
   | Role | Op  | Delta | Role | Op  | Delta | Role | Op  | Delta |
   +------+-----+-------+------+-----+-------+------+-----+-------+



.. collapse:: trace sequence diagram (click to toggle view)

   .. plantuml:: /developer/tests/diagrams/test_snapshots/test_snapshot_4_5.puml
          :scale: 100%


Section 6: Restarting node 3, should be behind enough to need snapshot transfer
===============================================================================



.. collapse:: section 6 trace table (click to toggle view)

   - See :ref:`Trace Table Legend` for help interpreting table contents

   +------+-----+-------+------+-----+-------+------+-----+-------+
   | N-1  | N-1 | N-1   | N-2  | N-2 | N-2   | N-3  | N-3 | N-3   |
   +------+-----+-------+------+-----+-------+------+-----+-------+
   | Role | Op  | Delta | Role | Op  | Delta | Role | Op  | Delta |
   +------+-----+-------+------+-----+-------+------+-----+-------+



.. collapse:: trace sequence diagram (click to toggle view)

   .. plantuml:: /developer/tests/diagrams/test_snapshots/test_snapshot_4_6.puml
          :scale: 100%


