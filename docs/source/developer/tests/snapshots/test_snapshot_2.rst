.. _test_snapshot_2:

=============================================
Test test_snapshot_2 from file test_snapshots
=============================================


    Test the simplest snapshot process, at a follower in a quiet cluster. After
    it is installed, have that node become the leader and make sure new commands
    work.

    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    
    

Section 1: Running election to elect node 1
===========================================


Raft features used:

.. include:: /developer/tests/features/leader_election/short.rst

.. collapse:: leader_election details (click to toggle view)

   .. include:: /developer/tests/features/leader_election/features.rst

   .. include:: /developer/tests/features/leader_election/narative.rst


.. include..  :: /developer/tests/features/leader_election/branches/without_pre_vote/short.rst

.. collapse:: leader_election/branches/without_pre_vote details (click to toggle view)

   .. include:: /developer/tests/features/leader_election/branches/without_pre_vote/features.rst

   .. include:: /developer/tests/features/leader_election/branches/without_pre_vote/narative.rst




.. collapse:: section 1 trace table (click to toggle view)

   - See :ref:`Trace Table Legend` for help interpreting table contents

   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | N-1  | N-1                         | N-1       | N-2  | N-2                         | N-2       | N-3  | N-3                         | N-3       |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | Role | Op                          | Delta     | Role | Op                          | Delta     | Role | Op                          | Delta     |
   +======+=============================+===========+======+=============================+===========+======+=============================+===========+
   | CNDI | NEW ROLE                    |           | FLWR |                             |           | FLWR |                             |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | CNDI | poll+N-2 t-1 li-0 lt-0      |           | FLWR |                             |           | FLWR |                             |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | CNDI | poll+N-3 t-1 li-0 lt-0      |           | FLWR |                             |           | FLWR |                             |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | CNDI |                             |           | FLWR | N-1+poll t-1 li-0 lt-0      | t-1       | FLWR |                             |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | CNDI |                             |           | FLWR | vote+N-1 yes-True           |           | FLWR |                             |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | CNDI |                             |           | FLWR |                             |           | FLWR | N-1+poll t-1 li-0 lt-0      | t-1       |
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



.. collapse:: trace sequence diagram (click to toggle view)

   .. plantuml:: /developer/tests/diagrams/test_snapshots/test_snapshot_2_1.puml
          :scale: 100%


Section 2: Node 1 is leader, running commands by indirect fake path
===================================================================


Raft features used:

.. include:: /developer/tests/features/state_machine_command/short.rst

.. collapse:: state_machine_command details (click to toggle view)

   .. include:: /developer/tests/features/state_machine_command/features.rst

   .. include:: /developer/tests/features/state_machine_command/narative.rst


.. include..  :: /developer/tests/features/state_machine_command/branches/all_in_sync/short.rst

.. collapse:: state_machine_command/branches/all_in_sync details (click to toggle view)

   .. include:: /developer/tests/features/state_machine_command/branches/all_in_sync/features.rst

   .. include:: /developer/tests/features/state_machine_command/branches/all_in_sync/narative.rst




.. collapse:: section 2 trace table (click to toggle view)

   - See :ref:`Trace Table Legend` for help interpreting table contents

   +------+-----+-------+------+-----+-------+------+-----+-------+
   | N-1  | N-1 | N-1   | N-2  | N-2 | N-2   | N-3  | N-3 | N-3   |
   +------+-----+-------+------+-----+-------+------+-----+-------+
   | Role | Op  | Delta | Role | Op  | Delta | Role | Op  | Delta |
   +------+-----+-------+------+-----+-------+------+-----+-------+



.. collapse:: trace sequence diagram (click to toggle view)

   .. plantuml:: /developer/tests/diagrams/test_snapshots/test_snapshot_2_2.puml
          :scale: 100%


Section 3: Node 2 has snapshot and empty log, switching it to leader
====================================================================


Raft features tested:

.. include:: /developer/tests/features/leader_election/short.rst

.. collapse:: leader_election details (click to toggle view)

   .. include:: /developer/tests/features/leader_election/features.rst

   .. include:: /developer/tests/features/leader_election/narative.rst


.. include..  :: /developer/tests/features/leader_election/branches/voluntary_step_down/short.rst

.. collapse:: leader_election/branches/voluntary_step_down details (click to toggle view)

   .. include:: /developer/tests/features/leader_election/branches/voluntary_step_down/features.rst

   .. include:: /developer/tests/features/leader_election/branches/voluntary_step_down/narative.rst


.. include:: /developer/tests/features/snapshots/short.rst

.. collapse:: snapshots details (click to toggle view)

   .. include:: /developer/tests/features/snapshots/features.rst

   .. include:: /developer/tests/features/snapshots/narative.rst


.. include..  :: /developer/tests/features/snapshots/branches/snapshot_based_leadership/short.rst

.. collapse:: snapshots/branches/snapshot_based_leadership details (click to toggle view)

   .. include:: /developer/tests/features/snapshots/branches/snapshot_based_leadership/features.rst

   .. include:: /developer/tests/features/snapshots/branches/snapshot_based_leadership/narative.rst


Raft features used:

.. include:: /developer/tests/features/snapshots/short.rst

.. collapse:: snapshots details (click to toggle view)

   .. include:: /developer/tests/features/snapshots/features.rst

   .. include:: /developer/tests/features/snapshots/narative.rst


.. include..  :: /developer/tests/features/snapshots/branches/follower_snapshot_creation/short.rst

.. collapse:: snapshots/branches/follower_snapshot_creation details (click to toggle view)

   .. include:: /developer/tests/features/snapshots/branches/follower_snapshot_creation/features.rst

   .. include:: /developer/tests/features/snapshots/branches/follower_snapshot_creation/narative.rst


.. include..  :: /developer/tests/features/snapshots/branches/log_compaction/short.rst

.. collapse:: snapshots/branches/log_compaction details (click to toggle view)

   .. include:: /developer/tests/features/snapshots/branches/log_compaction/features.rst

   .. include:: /developer/tests/features/snapshots/branches/log_compaction/narative.rst




.. collapse:: section 3 trace table (click to toggle view)

   - See :ref:`Trace Table Legend` for help interpreting table contents

   +------+-------------------------------+-------------+------+-------------------------------+------------+------+-------------------------------+-------------+
   | N-1  | N-1                           | N-1         | N-2  | N-2                           | N-2        | N-3  | N-3                           | N-3         |
   +------+-------------------------------+-------------+------+-------------------------------+------------+------+-------------------------------+-------------+
   | Role | Op                            | Delta       | Role | Op                            | Delta      | Role | Op                            | Delta       |
   +======+===============================+=============+======+===============================+============+======+===============================+=============+
   | FLWR | NEW ROLE                      |             | FLWR |                               |            | FLWR |                               |             |
   +------+-------------------------------+-------------+------+-------------------------------+------------+------+-------------------------------+-------------+
   | FLWR |                               |             | CNDI | NEW ROLE                      | t-2        | FLWR |                               |             |
   +------+-------------------------------+-------------+------+-------------------------------+------------+------+-------------------------------+-------------+
   | FLWR |                               |             | CNDI | poll+N-1 t-2 li-91 lt-1       |            | FLWR |                               |             |
   +------+-------------------------------+-------------+------+-------------------------------+------------+------+-------------------------------+-------------+
   | FLWR |                               |             | CNDI | poll+N-3 t-2 li-91 lt-1       |            | FLWR |                               |             |
   +------+-------------------------------+-------------+------+-------------------------------+------------+------+-------------------------------+-------------+
   | FLWR |                               |             | CNDI |                               |            | FLWR | N-2+poll t-2 li-91 lt-1       | t-2         |
   +------+-------------------------------+-------------+------+-------------------------------+------------+------+-------------------------------+-------------+
   | FLWR |                               |             | CNDI |                               |            | FLWR | vote+N-2 yes-True             |             |
   +------+-------------------------------+-------------+------+-------------------------------+------------+------+-------------------------------+-------------+
   | FLWR | N-2+poll t-2 li-91 lt-1       | t-2         | CNDI |                               |            | FLWR |                               |             |
   +------+-------------------------------+-------------+------+-------------------------------+------------+------+-------------------------------+-------------+
   | FLWR | vote+N-2 yes-True             |             | CNDI |                               |            | FLWR |                               |             |
   +------+-------------------------------+-------------+------+-------------------------------+------------+------+-------------------------------+-------------+
   | FLWR |                               |             | LEAD | N-3+vote yes-True             | lt-2 li-92 | FLWR |                               |             |
   +------+-------------------------------+-------------+------+-------------------------------+------------+------+-------------------------------+-------------+
   | FLWR |                               |             | LEAD | NEW ROLE                      |            | FLWR |                               |             |
   +------+-------------------------------+-------------+------+-------------------------------+------------+------+-------------------------------+-------------+
   | FLWR |                               |             | LEAD | ae+N-1 t-2 i-91 lt-1 e-1 c-91 |            | FLWR |                               |             |
   +------+-------------------------------+-------------+------+-------------------------------+------------+------+-------------------------------+-------------+
   | FLWR |                               |             | LEAD | ae+N-3 t-2 i-91 lt-1 e-1 c-91 |            | FLWR |                               |             |
   +------+-------------------------------+-------------+------+-------------------------------+------------+------+-------------------------------+-------------+
   | FLWR |                               |             | LEAD | N-1+vote yes-True             |            | FLWR |                               |             |
   +------+-------------------------------+-------------+------+-------------------------------+------------+------+-------------------------------+-------------+
   | FLWR |                               |             | LEAD |                               |            | FLWR | N-2+ae t-2 i-91 lt-1 e-1 c-91 | lt-2 li-92  |
   +------+-------------------------------+-------------+------+-------------------------------+------------+------+-------------------------------+-------------+
   | FLWR |                               |             | LEAD |                               |            | FLWR | N-3+ae_reply ok-True mi-92    |             |
   +------+-------------------------------+-------------+------+-------------------------------+------------+------+-------------------------------+-------------+
   | FLWR | N-2+ae t-2 i-91 lt-1 e-1 c-91 | lt-2 li-92  | LEAD |                               |            | FLWR |                               |             |
   +------+-------------------------------+-------------+------+-------------------------------+------------+------+-------------------------------+-------------+
   | FLWR | N-1+ae_reply ok-True mi-92    |             | LEAD |                               |            | FLWR |                               |             |
   +------+-------------------------------+-------------+------+-------------------------------+------------+------+-------------------------------+-------------+
   | FLWR |                               |             | LEAD | N-3+ae_reply ok-True mi-92    | ci-92      | FLWR |                               |             |
   +------+-------------------------------+-------------+------+-------------------------------+------------+------+-------------------------------+-------------+
   | FLWR |                               |             | LEAD | N-1+ae_reply ok-True mi-92    |            | FLWR |                               |             |
   +------+-------------------------------+-------------+------+-------------------------------+------------+------+-------------------------------+-------------+
   | FLWR |                               |             | LEAD | CMD START                     |            | FLWR |                               |             |
   +------+-------------------------------+-------------+------+-------------------------------+------------+------+-------------------------------+-------------+
   | FLWR |                               |             | LEAD | ae+N-1 t-2 i-92 lt-2 e-1 c-92 | li-93      | FLWR |                               |             |
   +------+-------------------------------+-------------+------+-------------------------------+------------+------+-------------------------------+-------------+
   | FLWR |                               |             | LEAD | ae+N-3 t-2 i-92 lt-2 e-1 c-92 |            | FLWR |                               |             |
   +------+-------------------------------+-------------+------+-------------------------------+------------+------+-------------------------------+-------------+
   | FLWR |                               |             | LEAD |                               |            | FLWR | N-2+ae t-2 i-92 lt-2 e-1 c-92 | li-93 ci-92 |
   +------+-------------------------------+-------------+------+-------------------------------+------------+------+-------------------------------+-------------+
   | FLWR |                               |             | LEAD |                               |            | FLWR | N-3+ae_reply ok-True mi-93    |             |
   +------+-------------------------------+-------------+------+-------------------------------+------------+------+-------------------------------+-------------+
   | FLWR | N-2+ae t-2 i-92 lt-2 e-1 c-92 | li-93 ci-92 | LEAD |                               |            | FLWR |                               |             |
   +------+-------------------------------+-------------+------+-------------------------------+------------+------+-------------------------------+-------------+
   | FLWR | N-1+ae_reply ok-True mi-93    |             | LEAD |                               |            | FLWR |                               |             |
   +------+-------------------------------+-------------+------+-------------------------------+------------+------+-------------------------------+-------------+
   | FLWR |                               |             | LEAD | N-3+ae_reply ok-True mi-93    | ci-93      | FLWR |                               |             |
   +------+-------------------------------+-------------+------+-------------------------------+------------+------+-------------------------------+-------------+
   | FLWR |                               |             | LEAD |                               |            | FLWR | N-2+ae t-2 i-93 lt-2 e-0 c-93 | ci-93       |
   +------+-------------------------------+-------------+------+-------------------------------+------------+------+-------------------------------+-------------+
   | FLWR |                               |             | LEAD | CMD DONE                      |            | FLWR |                               |             |
   +------+-------------------------------+-------------+------+-------------------------------+------------+------+-------------------------------+-------------+
   | FLWR | N-2+ae t-2 i-93 lt-2 e-0 c-93 | ci-93       | LEAD |                               |            | FLWR |                               |             |
   +------+-------------------------------+-------------+------+-------------------------------+------------+------+-------------------------------+-------------+
   | FLWR |                               |             | LEAD | N-1+ae_reply ok-True mi-93    |            | FLWR |                               |             |
   +------+-------------------------------+-------------+------+-------------------------------+------------+------+-------------------------------+-------------+
   | FLWR |                               |             | LEAD | sn+N-1 i-0                    |            | FLWR |                               |             |
   +------+-------------------------------+-------------+------+-------------------------------+------------+------+-------------------------------+-------------+
   | FLWR | N-2+snr i-0 s-True            |             | LEAD |                               |            | FLWR |                               |             |
   +------+-------------------------------+-------------+------+-------------------------------+------------+------+-------------------------------+-------------+



.. collapse:: trace sequence diagram (click to toggle view)

   .. plantuml:: /developer/tests/diagrams/test_snapshots/test_snapshot_2_3.puml
          :scale: 100%


