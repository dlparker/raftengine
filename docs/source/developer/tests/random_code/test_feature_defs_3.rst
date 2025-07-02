.. _test_feature_defs_3:

===================================================
Test test_feature_defs_3 from file test_random_code
===================================================


    This runs "commands" using highly granular control of test servers 
    so that basic bugs in the first command processing will show up at a detailed 
    level. It also tests that invalid command attempts receive the right response.
    Finally, it validates that crashing a follower, running a command, and recovering
    the follower eventually results in the crashed follower being in sync.
    
    The invalid commands tested are

    1. Sending a command request to a follower, which should result in a redirect
    2. Sending a command request to a candidate, which should result in a "retry", meaning
       that the cluster is currently unable to process commands, so a later retry is recommended

    The second test is performed by doing some artificial manipulation of the state of one of the
    nodes. It is pushed to become a candidate, which will caused it to increase its term. After
    the command is rejected with a retry, the candidate node is forced back to follower mode and
    its term is artificially adjusted down to zero so that it will accept the current leader.

    Because the term is now zero, when the former candidate node receives a heartbeat it
    will accept the current leader.

    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    

Section 1: Running normal election till fully replicated
========================================================

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
   | FLWR | STARTED                     |           | FLWR | STARTED                     |           | FLWR | STARTED                     |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | CNDI | NEW ROLE                    |           | FLWR |                             |           | FLWR |                             |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | CNDI | p_v_r+N-2 t-1 li-0 lt-0     |           | FLWR |                             |           | FLWR |                             |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | CNDI | p_v_r+N-3 t-1 li-0 lt-0     |           | FLWR |                             |           | FLWR |                             |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | CNDI |                             |           | FLWR | N-1+p_v_r t-1 li-0 lt-0     |           | FLWR |                             |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | CNDI |                             |           | FLWR | p_v+N-1 yes-True            |           | FLWR |                             |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | CNDI |                             |           | FLWR |                             |           | FLWR | N-1+p_v_r t-1 li-0 lt-0     |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | CNDI |                             |           | FLWR |                             |           | FLWR | p_v+N-1 yes-True            |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | CNDI | N-2+p_v yes-True            | t-1       | FLWR |                             |           | FLWR |                             |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | CNDI | poll+N-2 t-1 li-0 lt-1      |           | FLWR |                             |           | FLWR |                             |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | CNDI | poll+N-3 t-1 li-0 lt-1      |           | FLWR |                             |           | FLWR |                             |           |
   +------+-----------------------------+-----------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | CNDI | N-3+p_v yes-True            |           | FLWR |                             |           | FLWR |                             |           |
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



.. collapse:: trace sequence diagram (click to toggle view)

   .. plantuml:: /developer/tests/diagrams/test_random_code/test_feature_defs_3_1.puml
          :scale: 100%


Section 2: Run one command, normal sequence till leader commit
==============================================================

Raft features tested:

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

   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | N-1  | N-1                         | N-1   | N-2  | N-2                         | N-2   | N-3  | N-3                         | N-3   |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | Role | Op                          | Delta | Role | Op                          | Delta | Role | Op                          | Delta |
   +======+=============================+=======+======+=============================+=======+======+=============================+=======+
   | LEAD | CMD START                   |       | FLWR |                             |       | FLWR |                             |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | LEAD | ae+N-2 t-1 i-1 lt-1 e-1 c-1 | li-2  | FLWR |                             |       | FLWR |                             |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | LEAD |                             |       | FLWR | N-1+ae t-1 i-1 lt-1 e-1 c-1 | li-2  | FLWR |                             |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | LEAD |                             |       | FLWR | N-2+ae_reply ok-True mi-2   |       | FLWR |                             |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | LEAD | N-2+ae_reply ok-True mi-2   | ci-2  | FLWR |                             |       | FLWR |                             |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | LEAD | ae+N-3 t-1 i-1 lt-1 e-1 c-1 |       | FLWR |                             |       | FLWR |                             |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | LEAD |                             |       | FLWR |                             |       | FLWR | N-1+ae t-1 i-1 lt-1 e-1 c-1 | li-2  |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | LEAD |                             |       | FLWR |                             |       | FLWR | N-3+ae_reply ok-True mi-2   |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | LEAD | N-3+ae_reply ok-True mi-2   |       | FLWR |                             |       | FLWR |                             |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | LEAD | CMD DONE                    |       | FLWR |                             |       | FLWR |                             |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | LEAD | ae+N-2 t-1 i-2 lt-1 e-0 c-2 |       | FLWR |                             |       | FLWR |                             |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | LEAD | ae+N-3 t-1 i-2 lt-1 e-0 c-2 |       | FLWR |                             |       | FLWR |                             |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | LEAD |                             |       | FLWR | N-1+ae t-1 i-2 lt-1 e-0 c-2 | ci-2  | FLWR |                             |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | LEAD |                             |       | FLWR |                             |       | FLWR | N-1+ae t-1 i-2 lt-1 e-0 c-2 | ci-2  |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+



.. collapse:: trace sequence diagram (click to toggle view)

   .. plantuml:: /developer/tests/diagrams/test_random_code/test_feature_defs_3_2.puml
          :scale: 100%


Section 3: Trying to run command at follower, looking for redirect
==================================================================

Raft features tested:

.. include:: /developer/tests/features/state_machine_command/short.rst

.. collapse:: state_machine_command details (click to toggle view)

   .. include:: /developer/tests/features/state_machine_command/features.rst

   .. include:: /developer/tests/features/state_machine_command/narative.rst


.. include..  :: /developer/tests/features/state_machine_command/branches/request_redirect/short.rst

.. collapse:: state_machine_command/branches/request_redirect details (click to toggle view)

   .. include:: /developer/tests/features/state_machine_command/branches/request_redirect/features.rst

   .. include:: /developer/tests/features/state_machine_command/branches/request_redirect/narative.rst




.. collapse:: section 3 trace table (click to toggle view)

   - See :ref:`Trace Table Legend` for help interpreting table contents

   +------+-----+-------+------+-----+-------+------+-----------+-------+
   | N-1  | N-1 | N-1   | N-2  | N-2 | N-2   | N-3  | N-3       | N-3   |
   +------+-----+-------+------+-----+-------+------+-----------+-------+
   | Role | Op  | Delta | Role | Op  | Delta | Role | Op        | Delta |
   +======+=====+=======+======+=====+=======+======+===========+=======+
   | LEAD |     |       | FLWR |     |       | FLWR | CMD START |       |
   +------+-----+-------+------+-----+-------+------+-----------+-------+
   | LEAD |     |       | FLWR |     |       | FLWR | CMD DONE  |       |
   +------+-----+-------+------+-----+-------+------+-----------+-------+



.. collapse:: trace sequence diagram (click to toggle view)

   .. plantuml:: /developer/tests/diagrams/test_random_code/test_feature_defs_3_3.puml
          :scale: 100%


Section 4: Pushing one follower to candidate, then trying command to it, looking for retry
==========================================================================================



.. collapse:: section 4 trace table (click to toggle view)

   - See :ref:`Trace Table Legend` for help interpreting table contents

   +------+-----+-------+------+-----+-------+------+-----------+-------+
   | N-1  | N-1 | N-1   | N-2  | N-2 | N-2   | N-3  | N-3       | N-3   |
   +------+-----+-------+------+-----+-------+------+-----------+-------+
   | Role | Op  | Delta | Role | Op  | Delta | Role | Op        | Delta |
   +======+=====+=======+======+=====+=======+======+===========+=======+
   | LEAD |     |       | FLWR |     |       | CNDI | NEW ROLE  |       |
   +------+-----+-------+------+-----+-------+------+-----------+-------+
   | LEAD |     |       | FLWR |     |       | CNDI | CMD START |       |
   +------+-----+-------+------+-----+-------+------+-----------+-------+
   | LEAD |     |       | FLWR |     |       | CNDI | CMD DONE  |       |
   +------+-----+-------+------+-----+-------+------+-----------+-------+



.. collapse:: trace sequence diagram (click to toggle view)

   .. plantuml:: /developer/tests/diagrams/test_random_code/test_feature_defs_3_4.puml
          :scale: 100%


Section 5: Pushing Leader to send heartbeats, after forcing candidate's term back down
======================================================================================



.. collapse:: section 5 trace table (click to toggle view)

   - See :ref:`Trace Table Legend` for help interpreting table contents

   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | N-1  | N-1                         | N-1   | N-2  | N-2                         | N-2   | N-3  | N-3                         | N-3   |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | Role | Op                          | Delta | Role | Op                          | Delta | Role | Op                          | Delta |
   +======+=============================+=======+======+=============================+=======+======+=============================+=======+
   | LEAD | N-2+ae_reply ok-True mi-2   |       | FLWR |                             |       | CNDI |                             |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | LEAD | ae+N-2 t-1 i-2 lt-1 e-0 c-2 |       | FLWR |                             |       | CNDI |                             |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | LEAD |                             |       | FLWR | N-1+ae t-1 i-2 lt-1 e-0 c-2 |       | CNDI |                             |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | LEAD |                             |       | FLWR | N-2+ae_reply ok-True mi-2   |       | CNDI |                             |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | LEAD | N-3+ae_reply ok-True mi-2   |       | FLWR |                             |       | CNDI |                             |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | LEAD | ae+N-3 t-1 i-2 lt-1 e-0 c-2 |       | FLWR |                             |       | CNDI |                             |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | LEAD |                             |       | FLWR |                             |       | FLWR | N-1+ae t-1 i-2 lt-1 e-0 c-2 |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | LEAD |                             |       | FLWR |                             |       | FLWR | NEW ROLE                    |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | LEAD |                             |       | FLWR |                             |       | FLWR | N-3+ae_reply ok-True mi-2   |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | LEAD | N-2+ae_reply ok-True mi-2   |       | FLWR |                             |       | FLWR |                             |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | LEAD | N-3+ae_reply ok-True mi-2   |       | FLWR |                             |       | FLWR |                             |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+



.. collapse:: trace sequence diagram (click to toggle view)

   .. plantuml:: /developer/tests/diagrams/test_random_code/test_feature_defs_3_5.puml
          :scale: 100%


Section 6: Crashing one follower, then running command to ensure it works with only one follower
================================================================================================

Raft features tested:

.. include:: /developer/tests/features/state_machine_command/short.rst

.. collapse:: state_machine_command details (click to toggle view)

   .. include:: /developer/tests/features/state_machine_command/features.rst

   .. include:: /developer/tests/features/state_machine_command/narative.rst


.. include..  :: /developer/tests/features/state_machine_command/branches/minimal_node_count/short.rst

.. collapse:: state_machine_command/branches/minimal_node_count details (click to toggle view)

   .. include:: /developer/tests/features/state_machine_command/branches/minimal_node_count/features.rst

   .. include:: /developer/tests/features/state_machine_command/branches/minimal_node_count/narative.rst




.. collapse:: section 6 trace table (click to toggle view)

   - See :ref:`Trace Table Legend` for help interpreting table contents

   +------+-----------------------------+-------+------+-----------------------------+-------+------+-------+-------+
   | N-1  | N-1                         | N-1   | N-2  | N-2                         | N-2   | N-3  | N-3   | N-3   |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-------+-------+
   | Role | Op                          | Delta | Role | Op                          | Delta | Role | Op    | Delta |
   +======+=============================+=======+======+=============================+=======+======+=======+=======+
   | LEAD |                             |       | FLWR |                             |       | FLWR | CRASH |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-------+-------+
   | LEAD | CMD START                   |       | FLWR |                             |       | FLWR |       |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-------+-------+
   | LEAD | ae+N-2 t-1 i-2 lt-1 e-1 c-2 | li-3  | FLWR |                             |       | FLWR |       |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-------+-------+
   | LEAD | ae+N-3 t-1 i-2 lt-1 e-1 c-2 |       | FLWR |                             |       | FLWR |       |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-------+-------+
   | LEAD |                             |       | FLWR | N-1+ae t-1 i-2 lt-1 e-1 c-2 | li-3  | FLWR |       |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-------+-------+
   | LEAD |                             |       | FLWR | N-2+ae_reply ok-True mi-3   |       | FLWR |       |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-------+-------+
   | LEAD | N-2+ae_reply ok-True mi-3   | ci-3  | FLWR |                             |       | FLWR |       |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-------+-------+
   | LEAD |                             |       | FLWR | N-1+ae t-1 i-3 lt-1 e-0 c-3 | ci-3  | FLWR |       |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-------+-------+
   | LEAD | CMD DONE                    |       | FLWR |                             |       | FLWR |       |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-------+-------+
   | LEAD | CMD START                   |       | FLWR |                             |       | FLWR |       |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-------+-------+
   | LEAD | ae+N-2 t-1 i-3 lt-1 e-1 c-3 | li-4  | FLWR |                             |       | FLWR |       |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-------+-------+
   | LEAD |                             |       | FLWR | N-2+ae_reply ok-True mi-3   |       | FLWR |       |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-------+-------+
   | LEAD |                             |       | FLWR | N-1+ae t-1 i-3 lt-1 e-1 c-3 | li-4  | FLWR |       |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-------+-------+
   | LEAD |                             |       | FLWR | N-2+ae_reply ok-True mi-4   |       | FLWR |       |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-------+-------+
   | LEAD | N-2+ae_reply ok-True mi-3   |       | FLWR |                             |       | FLWR |       |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-------+-------+
   | LEAD | ae+N-2 t-1 i-3 lt-1 e-1 c-3 |       | FLWR |                             |       | FLWR |       |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-------+-------+
   | LEAD | N-2+ae_reply ok-True mi-4   | ci-4  | FLWR |                             |       | FLWR |       |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-------+-------+
   | LEAD |                             |       | FLWR | N-1+ae t-1 i-3 lt-1 e-1 c-3 |       | FLWR |       |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-------+-------+
   | LEAD |                             |       | FLWR | N-2+ae_reply ok-True mi-4   |       | FLWR |       |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-------+-------+
   | LEAD |                             |       | FLWR | N-1+ae t-1 i-4 lt-1 e-0 c-4 | ci-4  | FLWR |       |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-------+-------+
   | LEAD | CMD DONE                    |       | FLWR |                             |       | FLWR |       |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-------+-------+
   | LEAD | N-2+ae_reply ok-True mi-4   |       | FLWR |                             |       | FLWR |       |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-------+-------+
   | LEAD |                             |       | FLWR | N-2+ae_reply ok-True mi-4   |       | FLWR |       |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-------+-------+
   | LEAD | N-2+ae_reply ok-True mi-4   |       | FLWR |                             |       | FLWR |       |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-------+-------+
   | LEAD | ae+N-2 t-1 i-4 lt-1 e-0 c-4 |       | FLWR |                             |       | FLWR |       |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-------+-------+
   | LEAD |                             |       | FLWR | N-1+ae t-1 i-4 lt-1 e-0 c-4 |       | FLWR |       |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-------+-------+
   | LEAD |                             |       | FLWR | N-2+ae_reply ok-True mi-4   |       | FLWR |       |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-------+-------+
   | LEAD | N-2+ae_reply ok-True mi-4   |       | FLWR |                             |       | FLWR |       |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-------+-------+
   | LEAD | ae+N-3 t-1 i-4 lt-1 e-0 c-4 |       | FLWR |                             |       | FLWR |       |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-------+-------+



.. collapse:: trace sequence diagram (click to toggle view)

   .. plantuml:: /developer/tests/diagrams/test_random_code/test_feature_defs_3_6.puml
          :scale: 100%


Section 7: Recovering follower, then pushing hearbeat to get it to catch up
===========================================================================

Raft features tested:

.. include:: /developer/tests/features/state_machine_command/short.rst

.. collapse:: state_machine_command details (click to toggle view)

   .. include:: /developer/tests/features/state_machine_command/features.rst

   .. include:: /developer/tests/features/state_machine_command/narative.rst


.. include..  :: /developer/tests/features/state_machine_command/branches/apply_on_delayed_replication/short.rst

.. collapse:: state_machine_command/branches/apply_on_delayed_replication details (click to toggle view)

   .. include:: /developer/tests/features/state_machine_command/branches/apply_on_delayed_replication/features.rst

   .. include:: /developer/tests/features/state_machine_command/branches/apply_on_delayed_replication/narative.rst


Raft features used:

.. include:: /developer/tests/features/log_replication/short.rst

.. collapse:: log_replication details (click to toggle view)

   .. include:: /developer/tests/features/log_replication/features.rst

   .. include:: /developer/tests/features/log_replication/narative.rst


.. include..  :: /developer/tests/features/log_replication/branches/slow_follower_backdown/short.rst

.. collapse:: log_replication/branches/slow_follower_backdown details (click to toggle view)

   .. include:: /developer/tests/features/log_replication/branches/slow_follower_backdown/features.rst

   .. include:: /developer/tests/features/log_replication/branches/slow_follower_backdown/narative.rst




.. collapse:: section 7 trace table (click to toggle view)

   - See :ref:`Trace Table Legend` for help interpreting table contents

   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-----------+
   | N-1  | N-1                         | N-1   | N-2  | N-2                         | N-2   | N-3  | N-3                         | N-3       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-----------+
   | Role | Op                          | Delta | Role | Op                          | Delta | Role | Op                          | Delta     |
   +======+=============================+=======+======+=============================+=======+======+=============================+===========+
   | LEAD |                             |       | FLWR |                             |       | FLWR | RESTART                     |           |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-----------+
   | LEAD | ae+N-2 t-1 i-4 lt-1 e-0 c-4 |       | FLWR |                             |       | FLWR |                             |           |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-----------+
   | LEAD |                             |       | FLWR | N-1+ae t-1 i-4 lt-1 e-0 c-4 |       | FLWR |                             |           |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-----------+
   | LEAD |                             |       | FLWR | N-2+ae_reply ok-True mi-4   |       | FLWR |                             |           |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-----------+
   | LEAD | N-2+ae_reply ok-True mi-4   |       | FLWR |                             |       | FLWR |                             |           |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-----------+
   | LEAD | ae+N-3 t-1 i-4 lt-1 e-0 c-4 |       | FLWR |                             |       | FLWR |                             |           |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-----------+
   | LEAD |                             |       | FLWR |                             |       | FLWR | N-1+ae t-1 i-4 lt-1 e-0 c-4 |           |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-----------+
   | LEAD |                             |       | FLWR |                             |       | FLWR | N-3+ae_reply ok-False mi-2  |           |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-----------+
   | LEAD | N-3+ae_reply ok-False mi-2  |       | FLWR |                             |       | FLWR |                             |           |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-----------+
   | LEAD | ae+N-3 t-1 i-2 lt-1 e-1 c-4 |       | FLWR |                             |       | FLWR |                             |           |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-----------+
   | LEAD |                             |       | FLWR |                             |       | FLWR | N-1+ae t-1 i-2 lt-1 e-1 c-4 | li-3 ci-3 |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-----------+
   | LEAD |                             |       | FLWR |                             |       | FLWR | N-3+ae_reply ok-True mi-3   |           |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-----------+
   | LEAD | N-3+ae_reply ok-True mi-3   |       | FLWR |                             |       | FLWR |                             |           |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-----------+
   | LEAD | ae+N-3 t-1 i-3 lt-1 e-1 c-4 |       | FLWR |                             |       | FLWR |                             |           |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-----------+
   | LEAD |                             |       | FLWR |                             |       | FLWR | N-1+ae t-1 i-3 lt-1 e-1 c-4 | li-4 ci-4 |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-----------+
   | LEAD |                             |       | FLWR |                             |       | FLWR | N-3+ae_reply ok-True mi-4   |           |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-----------+
   | LEAD | N-3+ae_reply ok-True mi-4   |       | FLWR |                             |       | FLWR |                             |           |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-----------+



.. collapse:: trace sequence diagram (click to toggle view)

   .. plantuml:: /developer/tests/diagrams/test_random_code/test_feature_defs_3_7.puml
          :scale: 100%


