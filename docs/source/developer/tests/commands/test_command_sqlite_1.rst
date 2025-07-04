.. _test_command_sqlite_1:

====================================================
Test test_command_sqlite_1 from file test_commands_1
====================================================


    Test election and state machine command operations while using
    a SQLite implementation of the log storage. Most other tests use
    an in-memory log implementation, so this test validates that the
    basic Raft operations work correctly with persistent database storage.

    This test covers:
    - Leader election with pre-vote (using SQLite for vote persistence)
    - State machine command processing with database log storage
    - Log replication and commit notification with persistent storage
    - Validation that all Raft safety properties hold with SQLite backend

    The test ensures SQLite compatibility for core Raft operations including
    log entry persistence, term tracking, and vote recording. If other tests
    using SQLite encounter issues, this test helps isolate basic storage problems.

    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    

Section 1: Normal election
==========================


Raft features used:

.. include:: /developer/tests/features/leader_election/short.rst

.. collapse:: leader_election details (click to toggle view)

   .. include:: /developer/tests/features/leader_election/features.rst

   .. include:: /developer/tests/features/leader_election/narative.rst


.. include..  :: /developer/tests/features/leader_election/branches/all_yes_votes/short.rst

.. collapse:: leader_election/branches/all_yes_votes details (click to toggle view)

   .. include:: /developer/tests/features/leader_election/branches/all_yes_votes/features.rst

   .. include:: /developer/tests/features/leader_election/branches/all_yes_votes/narative.rst


.. include..  :: /developer/tests/features/leader_election/branches/all_yes_votes.with_pre_vote/short.rst

.. collapse:: leader_election/branches/all_yes_votes.with_pre_vote details (click to toggle view)

   .. include:: /developer/tests/features/leader_election/branches/all_yes_votes.with_pre_vote/features.rst

   .. include:: /developer/tests/features/leader_election/branches/all_yes_votes.with_pre_vote/narative.rst




.. collapse:: section 1 trace table (click to toggle view)

   - See :ref:`Trace Table Legend` for help interpreting table contents

   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | N-1  | N-1                         | N-1       | N-2  | N-2                         | N-2       | N-3  | N-3                         | N-3       |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | Role | Op                          | Delta     | Role | Op                          | Delta     | Role | Op                          | Delta     |
   +======+=============================+===========+======+=============================+===========+======+=============================+===========+
   | FLWR |                             |           | FLWR |                             |           | CNDI | NEW ROLE                    |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | FLWR |                             |           | FLWR |                             |           | CNDI | p_v_r+N-1 t-1 li-0 lt-0     |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | FLWR |                             |           | FLWR |                             |           | CNDI | p_v_r+N-2 t-1 li-0 lt-0     |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | FLWR | N-3+p_v_r t-1 li-0 lt-0     |           | FLWR |                             |           | CNDI |                             |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | FLWR | p_v+N-3 yes-True            |           | FLWR |                             |           | CNDI |                             |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | FLWR |                             |           | FLWR | N-3+p_v_r t-1 li-0 lt-0     |           | CNDI |                             |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | FLWR |                             |           | FLWR | p_v+N-3 yes-True            |           | CNDI |                             |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | FLWR |                             |           | FLWR |                             |           | CNDI | N-1+p_v yes-True            | t-1       |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | FLWR |                             |           | FLWR |                             |           | CNDI | poll+N-1 t-1 li-0 lt-1      |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | FLWR |                             |           | FLWR |                             |           | CNDI | poll+N-2 t-1 li-0 lt-1      |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | FLWR |                             |           | FLWR |                             |           | CNDI | N-2+p_v yes-True            |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | FLWR | N-3+poll t-1 li-0 lt-1      | t-1       | FLWR |                             |           | CNDI |                             |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | FLWR | vote+N-3 yes-True           |           | FLWR |                             |           | CNDI |                             |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | FLWR |                             |           | FLWR | N-3+poll t-1 li-0 lt-1      | t-1       | CNDI |                             |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | FLWR |                             |           | FLWR | vote+N-3 yes-True           |           | CNDI |                             |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | FLWR |                             |           | FLWR |                             |           | LEAD | N-1+vote yes-True           | lt-1 li-1 |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | FLWR |                             |           | FLWR |                             |           | LEAD | NEW ROLE                    |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | FLWR |                             |           | FLWR |                             |           | LEAD | ae+N-1 t-1 i-0 lt-0 e-1 c-0 |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | FLWR |                             |           | FLWR |                             |           | LEAD | ae+N-2 t-1 i-0 lt-0 e-1 c-0 |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | FLWR |                             |           | FLWR |                             |           | LEAD | N-2+vote yes-True           |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | FLWR | N-3+ae t-1 i-0 lt-0 e-1 c-0 | lt-1 li-1 | FLWR |                             |           | LEAD |                             |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | FLWR | N-1+ae_reply ok-True mi-1   |           | FLWR |                             |           | LEAD |                             |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | FLWR |                             |           | FLWR | N-3+ae t-1 i-0 lt-0 e-1 c-0 | lt-1 li-1 | LEAD |                             |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | FLWR |                             |           | FLWR | N-2+ae_reply ok-True mi-1   |           | LEAD |                             |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | FLWR |                             |           | FLWR |                             |           | LEAD | N-1+ae_reply ok-True mi-1   | ci-1      |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | FLWR |                             |           | FLWR |                             |           | LEAD | N-2+ae_reply ok-True mi-1   |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+



.. collapse:: trace sequence diagram (click to toggle view)

   .. plantuml:: /developer/tests/diagrams/test_commands_1/test_command_sqlite_1_1.puml
          :scale: 100%


Section 2: Run command and check results at all nodes
=====================================================


Raft features tested:

.. include:: /developer/tests/features/log_storage/short.rst

.. collapse:: log_storage details (click to toggle view)

   .. include:: /developer/tests/features/log_storage/features.rst

   .. include:: /developer/tests/features/log_storage/narative.rst


.. include..  :: /developer/tests/features/log_storage/branches/sqlite_compatibility/short.rst

.. collapse:: log_storage/branches/sqlite_compatibility details (click to toggle view)

   .. include:: /developer/tests/features/log_storage/branches/sqlite_compatibility/features.rst

   .. include:: /developer/tests/features/log_storage/branches/sqlite_compatibility/narative.rst


.. include:: /developer/tests/features/state_machine_command/short.rst

.. collapse:: state_machine_command details (click to toggle view)

   .. include:: /developer/tests/features/state_machine_command/features.rst

   .. include:: /developer/tests/features/state_machine_command/narative.rst


.. include..  :: /developer/tests/features/state_machine_command/branches/all_in_sync/short.rst

.. collapse:: state_machine_command/branches/all_in_sync details (click to toggle view)

   .. include:: /developer/tests/features/state_machine_command/branches/all_in_sync/features.rst

   .. include:: /developer/tests/features/state_machine_command/branches/all_in_sync/narative.rst


Raft features used:

.. include:: /developer/tests/features/log_replication/short.rst

.. collapse:: log_replication details (click to toggle view)

   .. include:: /developer/tests/features/log_replication/features.rst

   .. include:: /developer/tests/features/log_replication/narative.rst


.. include..  :: /developer/tests/features/log_replication/branches/normal_replication/short.rst

.. collapse:: log_replication/branches/normal_replication details (click to toggle view)

   .. include:: /developer/tests/features/log_replication/branches/normal_replication/features.rst

   .. include:: /developer/tests/features/log_replication/branches/normal_replication/narative.rst


.. include..  :: /developer/tests/features/log_replication/branches/heartbeat_only/short.rst

.. collapse:: log_replication/branches/heartbeat_only details (click to toggle view)

   .. include:: /developer/tests/features/log_replication/branches/heartbeat_only/features.rst

   .. include:: /developer/tests/features/log_replication/branches/heartbeat_only/narative.rst




.. collapse:: section 2 trace table (click to toggle view)

   - See :ref:`Trace Table Legend` for help interpreting table contents

   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | N-1  | N-1                         | N-1   | N-2  | N-2                         | N-2   | N-3  | N-3                         | N-3   |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | Role | Op                          | Delta | Role | Op                          | Delta | Role | Op                          | Delta |
   +======+=============================+=======+======+=============================+=======+======+=============================+=======+
   | FLWR |                             |       | FLWR |                             |       | LEAD | CMD START                   |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | FLWR |                             |       | FLWR |                             |       | LEAD | ae+N-1 t-1 i-1 lt-1 e-1 c-1 | li-2  |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | FLWR |                             |       | FLWR |                             |       | LEAD | ae+N-2 t-1 i-1 lt-1 e-1 c-1 |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | FLWR | N-3+ae t-1 i-1 lt-1 e-1 c-1 | li-2  | FLWR |                             |       | LEAD |                             |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | FLWR | N-1+ae_reply ok-True mi-2   |       | FLWR |                             |       | LEAD |                             |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | FLWR |                             |       | FLWR | N-3+ae t-1 i-1 lt-1 e-1 c-1 | li-2  | LEAD |                             |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | FLWR |                             |       | FLWR | N-2+ae_reply ok-True mi-2   |       | LEAD |                             |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | FLWR |                             |       | FLWR |                             |       | LEAD | N-1+ae_reply ok-True mi-2   | ci-2  |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | FLWR |                             |       | FLWR |                             |       | LEAD | N-2+ae_reply ok-True mi-2   |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | FLWR |                             |       | FLWR |                             |       | LEAD | CMD DONE                    |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | FLWR | N-3+ae t-1 i-2 lt-1 e-0 c-2 | ci-2  | FLWR |                             |       | LEAD |                             |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | FLWR |                             |       | FLWR | N-3+ae t-1 i-2 lt-1 e-0 c-2 | ci-2  | LEAD |                             |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | FLWR | N-1+ae_reply ok-True mi-2   |       | FLWR |                             |       | LEAD |                             |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | FLWR |                             |       | FLWR | N-2+ae_reply ok-True mi-2   |       | LEAD |                             |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | FLWR |                             |       | FLWR |                             |       | LEAD | N-1+ae_reply ok-True mi-2   |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | FLWR |                             |       | FLWR |                             |       | LEAD | N-2+ae_reply ok-True mi-2   |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+



.. collapse:: trace sequence diagram (click to toggle view)

   .. plantuml:: /developer/tests/diagrams/test_commands_1/test_command_sqlite_1_2.puml
          :scale: 100%


