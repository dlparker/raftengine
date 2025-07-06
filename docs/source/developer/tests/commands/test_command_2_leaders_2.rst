.. _test_command_2_leaders_2:

=======================================================
Test test_command_2_leaders_2 from file test_commands_1
=======================================================


    This function is called once by each of two actual test functions. Once with
    the "discard" flag False and once with it True.

    test_command_2_leaders_1 runs with discard = True

    test_command_2_leaders_2  runs with discard = False

    The sequence begins with a normal election, followed by a state machine command
    which all of the nodes replicate.

    Next there is a network problem and a new election is started. When the discard
    flag is True this looks like a regular partition type test, the new leader will
    take over and allow a new command. The rejoin of the old leader will proceed
    as normal.

    However, when the discard flag is False, the messages sent to and from the original
    leader will not be lost, they will be delivered when it rejoins. Although this
    sort of transient network problem is not common, it certainly can happen, and
    it is possible that a follower's leader lost timeout fires while leader
    heartbeats are delayed but not lost.

    For example, it is possible that the first leader sent heartbeats
    to the cluster that did not get delivered because of network, and
    just when the cluster gave up and called an election the leader
    host machine also had a massive slow down (maybe trying to switch
    networks but thrashing on low memory) such the the leader code
    could not execute for a second or so but the message delivery was
    never really blocked.  These are the sort of timing and network
    problem that Raft is meant to handle. They might be unlikely, but
    they are possible.

    Regardless of how the affected messages are handled, the rejoin should deliver the same
    result, the new leader's state being replicated to the old leader.

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

   .. plantuml:: /developer/tests/diagrams/test_commands_1/test_command_2_leaders_2_1.puml
          :scale: 100%


Section 2: Running command normally
===================================


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

   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | N-1  | N-1                         | N-1   | N-2  | N-2                         | N-2   | N-3  | N-3                         | N-3   |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | Role | Op                          | Delta | Role | Op                          | Delta | Role | Op                          | Delta |
   +======+=============================+=======+======+=============================+=======+======+=============================+=======+
   | LEAD | CMD START                   |       | FLWR |                             |       | FLWR |                             |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | LEAD | ae+N-2 t-1 i-1 lt-1 e-1 c-1 | li-2  | FLWR |                             |       | FLWR |                             |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | LEAD | ae+N-3 t-1 i-1 lt-1 e-1 c-1 |       | FLWR |                             |       | FLWR |                             |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | LEAD |                             |       | FLWR | N-1+ae t-1 i-1 lt-1 e-1 c-1 | li-2  | FLWR |                             |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | LEAD |                             |       | FLWR | N-2+ae_reply ok-True mi-2   |       | FLWR |                             |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | LEAD |                             |       | FLWR |                             |       | FLWR | N-1+ae t-1 i-1 lt-1 e-1 c-1 | li-2  |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | LEAD |                             |       | FLWR |                             |       | FLWR | N-3+ae_reply ok-True mi-2   |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | LEAD | N-2+ae_reply ok-True mi-2   | ci-2  | FLWR |                             |       | FLWR |                             |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | LEAD | N-3+ae_reply ok-True mi-2   |       | FLWR |                             |       | FLWR |                             |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | LEAD |                             |       | FLWR | N-1+ae t-1 i-2 lt-1 e-0 c-2 | ci-2  | FLWR |                             |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | LEAD |                             |       | FLWR |                             |       | FLWR | N-1+ae t-1 i-2 lt-1 e-0 c-2 | ci-2  |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | LEAD | CMD DONE                    |       | FLWR |                             |       | FLWR |                             |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+



.. collapse:: trace sequence diagram (click to toggle view)

   .. plantuml:: /developer/tests/diagrams/test_commands_1/test_command_2_leaders_2_2.puml
          :scale: 100%


Section 3: Simlating network/speed problems for leader and starting election at node 2 
=======================================================================================


Raft features used:

.. include:: /developer/tests/features/network_partition/short.rst

.. collapse:: network_partition details (click to toggle view)

   .. include:: /developer/tests/features/network_partition/features.rst

   .. include:: /developer/tests/features/network_partition/narative.rst


.. include..  :: /developer/tests/features/network_partition/branches/leader_isolation/short.rst

.. collapse:: network_partition/branches/leader_isolation details (click to toggle view)

   .. include:: /developer/tests/features/network_partition/branches/leader_isolation/features.rst

   .. include:: /developer/tests/features/network_partition/branches/leader_isolation/narative.rst


.. include:: /developer/tests/features/leader_election/short.rst

.. collapse:: leader_election details (click to toggle view)

   .. include:: /developer/tests/features/leader_election/features.rst

   .. include:: /developer/tests/features/leader_election/narative.rst


.. include..  :: /developer/tests/features/leader_election/branches/partition_recovery/short.rst

.. collapse:: leader_election/branches/partition_recovery details (click to toggle view)

   .. include:: /developer/tests/features/leader_election/branches/partition_recovery/features.rst

   .. include:: /developer/tests/features/leader_election/branches/partition_recovery/narative.rst




.. collapse:: section 3 trace table (click to toggle view)

   - See :ref:`Trace Table Legend` for help interpreting table contents

   +------+-----+-------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | N-1  | N-1 | N-1   | N-2  | N-2                         | N-2       | N-3  | N-3                         | N-3       |
   +------+-----+-------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | Role | Op  | Delta | Role | Op                          | Delta     | Role | Op                          | Delta     |
   +======+=====+=======+======+=============================+===========+======+=============================+===========+
   | LEAD |     |       | CNDI | NEW ROLE                    |           | FLWR |                             |           |
   +------+-----+-------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | LEAD |     |       | CNDI | N-2+ae_reply ok-True mi-2   |           | FLWR |                             |           |
   +------+-----+-------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | LEAD |     |       | CNDI | p_v_r+N-1 t-2 li-2 lt-1     |           | FLWR |                             |           |
   +------+-----+-------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | LEAD |     |       | CNDI | p_v_r+N-3 t-2 li-2 lt-1     |           | FLWR |                             |           |
   +------+-----+-------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | LEAD |     |       | CNDI |                             |           | FLWR | N-3+ae_reply ok-True mi-2   |           |
   +------+-----+-------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | LEAD |     |       | CNDI |                             |           | FLWR | N-2+p_v_r t-2 li-2 lt-1     |           |
   +------+-----+-------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | LEAD |     |       | CNDI |                             |           | FLWR | p_v+N-2 yes-True            |           |
   +------+-----+-------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | LEAD |     |       | CNDI | N-3+p_v yes-True            | t-2       | FLWR |                             |           |
   +------+-----+-------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | LEAD |     |       | CNDI | poll+N-1 t-2 li-2 lt-2      |           | FLWR |                             |           |
   +------+-----+-------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | LEAD |     |       | CNDI | poll+N-3 t-2 li-2 lt-2      |           | FLWR |                             |           |
   +------+-----+-------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | LEAD |     |       | CNDI |                             |           | FLWR | N-2+poll t-2 li-2 lt-2      | t-2       |
   +------+-----+-------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | LEAD |     |       | CNDI |                             |           | FLWR | vote+N-2 yes-True           |           |
   +------+-----+-------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | LEAD |     |       | LEAD | N-3+vote yes-True           | lt-2 li-3 | FLWR |                             |           |
   +------+-----+-------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | LEAD |     |       | LEAD | NEW ROLE                    |           | FLWR |                             |           |
   +------+-----+-------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | LEAD |     |       | LEAD | ae+N-1 t-2 i-2 lt-1 e-1 c-2 |           | FLWR |                             |           |
   +------+-----+-------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | LEAD |     |       | LEAD | ae+N-3 t-2 i-2 lt-1 e-1 c-2 |           | FLWR |                             |           |
   +------+-----+-------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | LEAD |     |       | LEAD |                             |           | FLWR | N-2+ae t-2 i-2 lt-1 e-1 c-2 | lt-2 li-3 |
   +------+-----+-------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | LEAD |     |       | LEAD |                             |           | FLWR | N-3+ae_reply ok-True mi-3   |           |
   +------+-----+-------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | LEAD |     |       | LEAD | N-3+ae_reply ok-True mi-3   | ci-3      | FLWR |                             |           |
   +------+-----+-------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | LEAD |     |       | LEAD | CMD START                   |           | FLWR |                             |           |
   +------+-----+-------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | LEAD |     |       | LEAD | ae+N-3 t-2 i-3 lt-2 e-1 c-3 | li-4      | FLWR |                             |           |
   +------+-----+-------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | LEAD |     |       | LEAD |                             |           | FLWR | N-2+ae t-2 i-3 lt-2 e-1 c-3 | li-4      |
   +------+-----+-------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | LEAD |     |       | LEAD |                             |           | FLWR | N-3+ae_reply ok-True mi-4   |           |
   +------+-----+-------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | LEAD |     |       | LEAD | N-3+ae_reply ok-True mi-4   | ci-4      | FLWR |                             |           |
   +------+-----+-------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | LEAD |     |       | LEAD |                             |           | FLWR | N-2+ae t-2 i-4 lt-2 e-0 c-4 | ci-4      |
   +------+-----+-------+------+-----------------------------+-----------+------+-----------------------------+-----------+
   | LEAD |     |       | LEAD | CMD DONE                    |           | FLWR |                             |           |
   +------+-----+-------+------+-----------------------------+-----------+------+-----------------------------+-----------+



.. collapse:: trace sequence diagram (click to toggle view)

   .. plantuml:: /developer/tests/diagrams/test_commands_1/test_command_2_leaders_2_3.puml
          :scale: 100%


Section 4: Letting old leader rejoin network and delivering all lost messages
=============================================================================


Raft features tested:

.. include:: /developer/tests/features/network_partition/short.rst

.. collapse:: network_partition details (click to toggle view)

   .. include:: /developer/tests/features/network_partition/features.rst

   .. include:: /developer/tests/features/network_partition/narative.rst


.. include..  :: /developer/tests/features/network_partition/branches/delayed_message_delivery/short.rst

.. collapse:: network_partition/branches/delayed_message_delivery details (click to toggle view)

   .. include:: /developer/tests/features/network_partition/branches/delayed_message_delivery/features.rst

   .. include:: /developer/tests/features/network_partition/branches/delayed_message_delivery/narative.rst




.. collapse:: section 4 trace table (click to toggle view)

   - See :ref:`Trace Table Legend` for help interpreting table contents

   +------+-----------------------------+-----------+------+-----------------------------+-------+------+---------------------------+-------+
   | N-1  | N-1                         | N-1       | N-2  | N-2                         | N-2   | N-3  | N-3                       | N-3   |
   +------+-----------------------------+-----------+------+-----------------------------+-------+------+---------------------------+-------+
   | Role | Op                          | Delta     | Role | Op                          | Delta | Role | Op                        | Delta |
   +======+=============================+===========+======+=============================+=======+======+===========================+=======+
   | LEAD | N-2+ae_reply ok-True mi-2   |           | LEAD |                             |       | FLWR |                           |       |
   +------+-----------------------------+-----------+------+-----------------------------+-------+------+---------------------------+-------+
   | LEAD |                             |           | LEAD |                             |       | FLWR | N-3+ae_reply ok-True mi-4 |       |
   +------+-----------------------------+-----------+------+-----------------------------+-------+------+---------------------------+-------+
   | LEAD | N-2+p_v_r t-2 li-2 lt-1     |           | LEAD |                             |       | FLWR |                           |       |
   +------+-----------------------------+-----------+------+-----------------------------+-------+------+---------------------------+-------+
   | LEAD | p_v+N-2 yes-True            |           | LEAD |                             |       | FLWR |                           |       |
   +------+-----------------------------+-----------+------+-----------------------------+-------+------+---------------------------+-------+
   | LEAD |                             |           | LEAD | N-3+ae_reply ok-True mi-4   |       | FLWR |                           |       |
   +------+-----------------------------+-----------+------+-----------------------------+-------+------+---------------------------+-------+
   | LEAD | N-3+ae_reply ok-True mi-2   |           | LEAD |                             |       | FLWR |                           |       |
   +------+-----------------------------+-----------+------+-----------------------------+-------+------+---------------------------+-------+
   | LEAD |                             |           | LEAD | N-1+p_v yes-True            |       | FLWR |                           |       |
   +------+-----------------------------+-----------+------+-----------------------------+-------+------+---------------------------+-------+
   | FLWR | N-2+poll t-2 li-2 lt-2      | t-2       | LEAD |                             |       | FLWR |                           |       |
   +------+-----------------------------+-----------+------+-----------------------------+-------+------+---------------------------+-------+
   | FLWR | NEW ROLE                    |           | LEAD |                             |       | FLWR |                           |       |
   +------+-----------------------------+-----------+------+-----------------------------+-------+------+---------------------------+-------+
   | FLWR | vote+N-2 yes-True           |           | LEAD |                             |       | FLWR |                           |       |
   +------+-----------------------------+-----------+------+-----------------------------+-------+------+---------------------------+-------+
   | FLWR |                             |           | LEAD | N-1+vote yes-True           |       | FLWR |                           |       |
   +------+-----------------------------+-----------+------+-----------------------------+-------+------+---------------------------+-------+
   | FLWR | N-2+ae t-2 i-2 lt-1 e-1 c-2 | lt-2 li-3 | LEAD |                             |       | FLWR |                           |       |
   +------+-----------------------------+-----------+------+-----------------------------+-------+------+---------------------------+-------+
   | FLWR | N-1+ae_reply ok-True mi-3   |           | LEAD |                             |       | FLWR |                           |       |
   +------+-----------------------------+-----------+------+-----------------------------+-------+------+---------------------------+-------+
   | FLWR |                             |           | LEAD | N-1+ae_reply ok-True mi-3   |       | FLWR |                           |       |
   +------+-----------------------------+-----------+------+-----------------------------+-------+------+---------------------------+-------+
   | FLWR |                             |           | LEAD | ae+N-1 t-2 i-3 lt-2 e-1 c-4 |       | FLWR |                           |       |
   +------+-----------------------------+-----------+------+-----------------------------+-------+------+---------------------------+-------+
   | FLWR | N-2+ae t-2 i-4 lt-2 e-0 c-4 |           | LEAD |                             |       | FLWR |                           |       |
   +------+-----------------------------+-----------+------+-----------------------------+-------+------+---------------------------+-------+
   | FLWR | N-1+ae_reply ok-False mi-3  |           | LEAD |                             |       | FLWR |                           |       |
   +------+-----------------------------+-----------+------+-----------------------------+-------+------+---------------------------+-------+
   | FLWR |                             |           | LEAD | N-1+ae_reply ok-False mi-3  |       | FLWR |                           |       |
   +------+-----------------------------+-----------+------+-----------------------------+-------+------+---------------------------+-------+
   | FLWR |                             |           | LEAD | ae+N-1 t-2 i-3 lt-2 e-1 c-4 |       | FLWR |                           |       |
   +------+-----------------------------+-----------+------+-----------------------------+-------+------+---------------------------+-------+
   | FLWR | N-2+ae t-2 i-3 lt-2 e-1 c-4 | li-4 ci-4 | LEAD |                             |       | FLWR |                           |       |
   +------+-----------------------------+-----------+------+-----------------------------+-------+------+---------------------------+-------+
   | FLWR | N-1+ae_reply ok-True mi-4   |           | LEAD |                             |       | FLWR |                           |       |
   +------+-----------------------------+-----------+------+-----------------------------+-------+------+---------------------------+-------+
   | FLWR |                             |           | LEAD | N-1+ae_reply ok-True mi-4   |       | FLWR |                           |       |
   +------+-----------------------------+-----------+------+-----------------------------+-------+------+---------------------------+-------+
   | FLWR | N-2+ae t-2 i-3 lt-2 e-1 c-4 |           | LEAD |                             |       | FLWR |                           |       |
   +------+-----------------------------+-----------+------+-----------------------------+-------+------+---------------------------+-------+
   | FLWR | N-1+ae_reply ok-True mi-4   |           | LEAD |                             |       | FLWR |                           |       |
   +------+-----------------------------+-----------+------+-----------------------------+-------+------+---------------------------+-------+
   | FLWR |                             |           | LEAD | N-1+ae_reply ok-True mi-4   |       | FLWR |                           |       |
   +------+-----------------------------+-----------+------+-----------------------------+-------+------+---------------------------+-------+



.. collapse:: trace sequence diagram (click to toggle view)

   .. plantuml:: /developer/tests/diagrams/test_commands_1/test_command_2_leaders_2_4.puml
          :scale: 100%


Section 5: New leader sending heartbeats
========================================


Raft features used:

.. include:: /developer/tests/features/log_replication/short.rst

.. collapse:: log_replication details (click to toggle view)

   .. include:: /developer/tests/features/log_replication/features.rst

   .. include:: /developer/tests/features/log_replication/narative.rst


.. include..  :: /developer/tests/features/log_replication/branches/heartbeat_only/short.rst

.. collapse:: log_replication/branches/heartbeat_only details (click to toggle view)

   .. include:: /developer/tests/features/log_replication/branches/heartbeat_only/features.rst

   .. include:: /developer/tests/features/log_replication/branches/heartbeat_only/narative.rst




.. collapse:: section 5 trace table (click to toggle view)

   - See :ref:`Trace Table Legend` for help interpreting table contents

   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | N-1  | N-1                         | N-1   | N-2  | N-2                         | N-2   | N-3  | N-3                         | N-3   |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | Role | Op                          | Delta | Role | Op                          | Delta | Role | Op                          | Delta |
   +======+=============================+=======+======+=============================+=======+======+=============================+=======+
   | FLWR |                             |       | LEAD | ae+N-1 t-2 i-4 lt-2 e-0 c-4 |       | FLWR |                             |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | FLWR | N-2+ae t-2 i-4 lt-2 e-0 c-4 |       | LEAD |                             |       | FLWR |                             |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | FLWR | N-1+ae_reply ok-True mi-4   |       | LEAD |                             |       | FLWR |                             |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | FLWR |                             |       | LEAD | N-1+ae_reply ok-True mi-4   |       | FLWR |                             |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | FLWR |                             |       | LEAD | ae+N-3 t-2 i-4 lt-2 e-0 c-4 |       | FLWR |                             |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | FLWR |                             |       | LEAD |                             |       | FLWR | N-2+ae t-2 i-4 lt-2 e-0 c-4 |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | FLWR |                             |       | LEAD |                             |       | FLWR | N-3+ae_reply ok-True mi-4   |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+
   | FLWR |                             |       | LEAD | N-3+ae_reply ok-True mi-4   |       | FLWR |                             |       |
   +------+-----------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-------+



.. collapse:: trace sequence diagram (click to toggle view)

   .. plantuml:: /developer/tests/diagrams/test_commands_1/test_command_2_leaders_2_5.puml
          :scale: 100%


