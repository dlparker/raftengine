.. _test_election_1:

===============================================
Test test_election_1 from file test_elections_1
===============================================



    This runs the election happy path, everybody has same state, only one server
    runs for leader, everybody responds correctly. It is written
    using the most granular control provided by the PausingServer
    class, controlling the message movement steps directly (for
    the most part). The cluster is three nodes. Prevote is disabled for this test.

    If some basic error is introduced in the election related code, it will
    show up here with the most detail.

    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    

Section 1: Command triggering node one to start election
========================================================




.. collapse:: section 1 trace table (click to toggle view)

   - See :ref:`Trace Table Legend` for help interpreting table contents

   +------+------------------------+-----------+------+------------------------+-------+------+------------------------+-------+
   | N-1  | N-1                    | N-1       | N-2  | N-2                    | N-2   | N-3  | N-3                    | N-3   |
   +------+------------------------+-----------+------+------------------------+-------+------+------------------------+-------+
   | Role | Op                     | Delta     | Role | Op                     | Delta | Role | Op                     | Delta |
   +======+========================+===========+======+========================+=======+======+========================+=======+
   | CNDI | NEW ROLE               |           | FLWR |                        |       | FLWR |                        |       |
   +------+------------------------+-----------+------+------------------------+-------+------+------------------------+-------+
   | CNDI | poll+N-2 t-1 li-0 lt-1 |           | FLWR |                        |       | FLWR |                        |       |
   +------+------------------------+-----------+------+------------------------+-------+------+------------------------+-------+
   | CNDI | poll+N-3 t-1 li-0 lt-1 |           | FLWR |                        |       | FLWR |                        |       |
   +------+------------------------+-----------+------+------------------------+-------+------+------------------------+-------+
   | CNDI |                        |           | FLWR | N-1+poll t-1 li-0 lt-1 | t-1   | FLWR |                        |       |
   +------+------------------------+-----------+------+------------------------+-------+------+------------------------+-------+
   | CNDI |                        |           | FLWR | vote+N-1 yes-True      |       | FLWR |                        |       |
   +------+------------------------+-----------+------+------------------------+-------+------+------------------------+-------+
   | CNDI |                        |           | FLWR |                        |       | FLWR | N-1+poll t-1 li-0 lt-1 | t-1   |
   +------+------------------------+-----------+------+------------------------+-------+------+------------------------+-------+
   | CNDI |                        |           | FLWR |                        |       | FLWR | vote+N-1 yes-True      |       |
   +------+------------------------+-----------+------+------------------------+-------+------+------------------------+-------+
   | LEAD | N-2+vote yes-True      | lt-1 li-1 | FLWR |                        |       | FLWR |                        |       |
   +------+------------------------+-----------+------+------------------------+-------+------+------------------------+-------+
   | LEAD | NEW ROLE               |           | FLWR |                        |       | FLWR |                        |       |
   +------+------------------------+-----------+------+------------------------+-------+------+------------------------+-------+
   | LEAD | N-3+vote yes-True      |           | FLWR |                        |       | FLWR |                        |       |
   +------+------------------------+-----------+------+------------------------+-------+------+------------------------+-------+



.. collapse:: trace sequence diagram (click to toggle view)

   .. plantuml:: /developer/tests/diagrams/test_elections_1/test_election_1_1.puml
          :scale: 100%


Section 2: Node 1 is now leader, so it should declare the new term with a TERM_START log record
===============================================================================================




.. collapse:: section 2 trace table (click to toggle view)

   - See :ref:`Trace Table Legend` for help interpreting table contents

   +------+-----------------------------+-------+------+-----+-------+------+-----+-------+
   | N-1  | N-1                         | N-1   | N-2  | N-2 | N-2   | N-3  | N-3 | N-3   |
   +------+-----------------------------+-------+------+-----+-------+------+-----+-------+
   | Role | Op                          | Delta | Role | Op  | Delta | Role | Op  | Delta |
   +======+=============================+=======+======+=====+=======+======+=====+=======+
   | LEAD | ae+N-2 t-1 i-0 lt-0 e-1 c-0 |       | FLWR |     |       | FLWR |     |       |
   +------+-----------------------------+-------+------+-----+-------+------+-----+-------+
   | LEAD | ae+N-3 t-1 i-0 lt-0 e-1 c-0 |       | FLWR |     |       | FLWR |     |       |
   +------+-----------------------------+-------+------+-----+-------+------+-----+-------+



.. collapse:: trace sequence diagram (click to toggle view)

   .. plantuml:: /developer/tests/diagrams/test_elections_1/test_election_1_2.puml
          :scale: 100%


Section 3: Node 1 should get success replies to append entries from nodes 2 and 3
=================================================================================




.. collapse:: section 3 trace table (click to toggle view)

   - See :ref:`Trace Table Legend` for help interpreting table contents

   +------+---------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-----------+
   | N-1  | N-1                       | N-1   | N-2  | N-2                         | N-2   | N-3  | N-3                         | N-3       |
   +------+---------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-----------+
   | Role | Op                        | Delta | Role | Op                          | Delta | Role | Op                          | Delta     |
   +======+===========================+=======+======+=============================+=======+======+=============================+===========+
   | LEAD |                           |       | FLWR | N-1+ae t-1 i-0 lt-0 e-1 c-0 |       | FLWR |                             |           |
   +------+---------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-----------+
   | LEAD |                           |       | FLWR | N-2+ae_reply ok-True mi-1   |       | FLWR |                             |           |
   +------+---------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-----------+
   | LEAD |                           |       | FLWR |                             |       | FLWR | N-1+ae t-1 i-0 lt-0 e-1 c-0 | lt-1 li-1 |
   +------+---------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-----------+
   | LEAD |                           |       | FLWR |                             |       | FLWR | N-3+ae_reply ok-True mi-1   |           |
   +------+---------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-----------+
   | LEAD | N-2+ae_reply ok-True mi-1 | ci-1  | FLWR |                             |       | FLWR |                             |           |
   +------+---------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-----------+
   | LEAD | N-3+ae_reply ok-True mi-1 |       | FLWR |                             |       | FLWR |                             |           |
   +------+---------------------------+-------+------+-----------------------------+-------+------+-----------------------------+-----------+



.. collapse:: trace sequence diagram (click to toggle view)

   .. plantuml:: /developer/tests/diagrams/test_elections_1/test_election_1_3.puml
          :scale: 100%


