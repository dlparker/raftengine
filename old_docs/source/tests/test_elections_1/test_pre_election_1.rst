.. _test_pre_election_1:

Test test_pre_election_1 from file test_elections_1
===================================================



    This runs the election happy path, with prevote enabled
    everybody has same state, only one server
    runs for leader, everybody responds correctly. It is written
    using the most granular control provided by the PausingServer
    class, controlling the message movement steps directly (for
    the most part). The cluster is three nodes.

    If some basic error is introduced in the election related code, it will
    show up here with the most detail.

    Timers are disabled, so all timer driven operations such as heartbeats are manually triggered.
    

Raft features in test
=====================

Features under focus
--------------------

* **election**: The voting process of an election, followed by the TERM_START log record propogation.
  Primary explation is in the thesis section 3.4, with the post election TERM_START record mentioned only in
  section 6.4.1 under read only client queries


Test Sequence Diagram
=====================

.. plantuml:: ../../_static/diagrams/test_trace_pics/test_elections_1/test_pre_election_1/diag1.puml
     :scale: 100%	      



Thesis Mapping for test_pre_election_1
======================================

The condensed sequence diagram above illustrates the Raft protocol’s election process with PreVote enabled, as implemented in RaftEngine’s ``test_pre_election_1``. Below, the diagram’s actions are mapped to sections of Diego Ongaro’s Raft thesis (`<https://github.com/ongardie/dissertation/blob/master/online.pdf>`__).

PreVote Phase
-------------
- **Actions**: Node 1 (N-1) sends PreVote requests (``p_v_r t-1 li-0 lt-0``) to Nodes 2 and 3, receiving affirmative responses (``p_v yes-True``).
- **Thesis Reference**: Section 3.4 (Election Voting) describes the PreVote mechanism, an extension to prevent disruptive elections by requiring candidates to confirm viability before incrementing terms. The diagram shows N-1 collecting PreVote approvals, ensuring it can safely proceed to the voting phase without risking term conflicts.

Voting Phase
------------
- **Actions**: N-1 sends vote requests (``poll t-1 li-0 lt-1``) to N-2 and N-3, receiving affirmative votes (``vote yes-True``), then transitions to Leader role.
- **Thesis Reference**: Section 3.4 details the RequestVote RPC process, where a candidate (N-1) solicits votes from followers (N-2, N-3). The diagram reflects N-1 achieving a majority (2/3 votes), allowing it to become leader, with term (``t-1``) and log indices (``li-1``, ``lt-1``) updated.

TERM_START Log Propagation
--------------------------
- **Actions**: N-1 (Leader) sends AppendEntries messages (``ae t-1 i-0 lt-0 e-1 c-0``) to N-2 and N-3, receiving successful replies (``ae_reply ok-True mi-1``), updating commit index (``ci-1``).
- **Thesis Reference**: Section 6.4.1 (Read-Only Client Queries) mentions the `TERM_START` log record, propagated by the leader to confirm its term. The diagram shows N-1 broadcasting this record via AppendEntries, with N-2 and N-3 acknowledging, aligning log indices (``li-1``) and terms (``lt-1``).

Notes
-----
- The PreVote and voting phases collectively implement the election process (Section 3.4), ensuring N-1’s leadership is stable and non-disruptive.
- The `TERM_START` propagation (Section 6.4.1) finalizes the election, enabling subsequent client operations.
- This “happy path” test avoids complexities like crashes or partitions, aligning with the thesis’s core protocol description.

	     

Test Sequence Table
=====================

- See :ref:`Trace Table Legend` for help interpreting table contents

Testing election with pre-vote enabled
--------------------------------------

+--------+-------------------------+-----------+-------+-------------------------+-------+-------+-------------------------+-------+
|  N-1   | N-1                     | N-1       | N-2   | N-2                     | N-2   | N-3   | N-3                     | N-3   |
+========+=========================+===========+=======+=========================+=======+=======+=========================+=======+
|  Role  | Op                      | Delta     | Role  | Op                      | Delta | Role  | Op                      | Delta |
+--------+-------------------------+-----------+-------+-------------------------+-------+-------+-------------------------+-------+
|  FLWR  | STARTED                 |           | FLWR  | STARTED                 |       | FLWR  | STARTED                 |       |
+--------+-------------------------+-----------+-------+-------------------------+-------+-------+-------------------------+-------+
|  CNDI  | NEW ROLE                |           | FLWR  |                         |       | FLWR  |                         |       |
+--------+-------------------------+-----------+-------+-------------------------+-------+-------+-------------------------+-------+
|  CNDI  | p_v_r+N-2 t-1 li-0 lt-0 |           | FLWR  |                         |       | FLWR  |                         |       |
+--------+-------------------------+-----------+-------+-------------------------+-------+-------+-------------------------+-------+
|  CNDI  | p_v_r+N-3 t-1 li-0 lt-0 |           | FLWR  |                         |       | FLWR  |                         |       |
+--------+-------------------------+-----------+-------+-------------------------+-------+-------+-------------------------+-------+
|  CNDI  |                         |           | FLWR  | N-1+p_v_r t-1 li-0 lt-0 |       | FLWR  |                         |       |
+--------+-------------------------+-----------+-------+-------------------------+-------+-------+-------------------------+-------+
|  CNDI  |                         |           | FLWR  | p_v+N-1 yes-True        |       | FLWR  |                         |       |
+--------+-------------------------+-----------+-------+-------------------------+-------+-------+-------------------------+-------+
|  CNDI  |                         |           | FLWR  |                         |       | FLWR  | N-1+p_v_r t-1 li-0 lt-0 |       |
+--------+-------------------------+-----------+-------+-------------------------+-------+-------+-------------------------+-------+
|  CNDI  |                         |           | FLWR  |                         |       | FLWR  | p_v+N-1 yes-True        |       |
+--------+-------------------------+-----------+-------+-------------------------+-------+-------+-------------------------+-------+
|  CNDI  | N-2+p_v yes-True        | t-1       | FLWR  |                         |       | FLWR  |                         |       |
+--------+-------------------------+-----------+-------+-------------------------+-------+-------+-------------------------+-------+
|  CNDI  | N-3+p_v yes-True        |           | FLWR  |                         |       | FLWR  |                         |       |
+--------+-------------------------+-----------+-------+-------------------------+-------+-------+-------------------------+-------+
|  CNDI  | poll+N-2 t-1 li-0 lt-1  |           | FLWR  |                         |       | FLWR  |                         |       |
+--------+-------------------------+-----------+-------+-------------------------+-------+-------+-------------------------+-------+
|  CNDI  | poll+N-3 t-1 li-0 lt-1  |           | FLWR  |                         |       | FLWR  |                         |       |
+--------+-------------------------+-----------+-------+-------------------------+-------+-------+-------------------------+-------+
|  CNDI  |                         |           | FLWR  | N-1+poll t-1 li-0 lt-1  | t-1   | FLWR  |                         |       |
+--------+-------------------------+-----------+-------+-------------------------+-------+-------+-------------------------+-------+
|  CNDI  |                         |           | FLWR  | vote+N-1 yes-True       |       | FLWR  |                         |       |
+--------+-------------------------+-----------+-------+-------------------------+-------+-------+-------------------------+-------+
|  CNDI  |                         |           | FLWR  |                         |       | FLWR  | N-1+poll t-1 li-0 lt-1  | t-1   |
+--------+-------------------------+-----------+-------+-------------------------+-------+-------+-------------------------+-------+
|  CNDI  |                         |           | FLWR  |                         |       | FLWR  | vote+N-1 yes-True       |       |
+--------+-------------------------+-----------+-------+-------------------------+-------+-------+-------------------------+-------+
|  LEAD  | N-2+vote yes-True       | lt-1 li-1 | FLWR  |                         |       | FLWR  |                         |       |
+--------+-------------------------+-----------+-------+-------------------------+-------+-------+-------------------------+-------+
|  LEAD  | NEW ROLE                |           | FLWR  |                         |       | FLWR  |                         |       |
+--------+-------------------------+-----------+-------+-------------------------+-------+-------+-------------------------+-------+
|  LEAD  | N-3+vote yes-True       |           | FLWR  |                         |       | FLWR  |                         |       |
+--------+-------------------------+-----------+-------+-------------------------+-------+-------+-------------------------+-------+


Node 1 is now leader, so it should declare the new term with a TERM_START log record
------------------------------------------------------------------------------------


+--------+-----------------------------+-------+-------+-----+-------+-------+-----+-------+
|  N-1   | N-1                         | N-1   | N-2   | N-2 | N-2   | N-3   | N-3 | N-3   |
+========+=============================+=======+=======+=====+=======+=======+=====+=======+
|  Role  | Op                          | Delta | Role  | Op  | Delta | Role  | Op  | Delta |
+--------+-----------------------------+-------+-------+-----+-------+-------+-----+-------+
|  LEAD  | ae+N-2 t-1 i-0 lt-0 e-1 c-0 |       | FLWR  |     |       | FLWR  |     |       |
+--------+-----------------------------+-------+-------+-----+-------+-------+-----+-------+
|  LEAD  | ae+N-3 t-1 i-0 lt-0 e-1 c-0 |       | FLWR  |     |       | FLWR  |     |       |
+--------+-----------------------------+-------+-------+-----+-------+-------+-----+-------+


Node 1 should get success replies to append entries from nodes 2 and 3
----------------------------------------------------------------------


+--------+---------------------------+-------+-------+-----------------------------+-------+-------+-----------------------------+-----------+
|  N-1   | N-1                       | N-1   | N-2   | N-2                         | N-2   | N-3   | N-3                         | N-3       |
+========+===========================+=======+=======+=============================+=======+=======+=============================+===========+
|  Role  | Op                        | Delta | Role  | Op                          | Delta | Role  | Op                          | Delta     |
+--------+---------------------------+-------+-------+-----------------------------+-------+-------+-----------------------------+-----------+
|  LEAD  |                           |       | FLWR  | N-1+ae t-1 i-0 lt-0 e-1 c-0 |       | FLWR  |                             |           |
+--------+---------------------------+-------+-------+-----------------------------+-------+-------+-----------------------------+-----------+
|  LEAD  |                           |       | FLWR  | ae_reply+N-1 ok-True mi-1   |       | FLWR  |                             |           |
+--------+---------------------------+-------+-------+-----------------------------+-------+-------+-----------------------------+-----------+
|  LEAD  |                           |       | FLWR  |                             |       | FLWR  | N-1+ae t-1 i-0 lt-0 e-1 c-0 | lt-1 li-1 |
+--------+---------------------------+-------+-------+-----------------------------+-------+-------+-----------------------------+-----------+
|  LEAD  |                           |       | FLWR  |                             |       | FLWR  | ae_reply+N-1 ok-True mi-1   |           |
+--------+---------------------------+-------+-------+-----------------------------+-------+-------+-----------------------------+-----------+
|  LEAD  | N-2+ae_reply ok-True mi-1 | ci-1  | FLWR  |                             |       | FLWR  |                             |           |
+--------+---------------------------+-------+-------+-----------------------------+-------+-------+-----------------------------+-----------+
|  LEAD  | N-3+ae_reply ok-True mi-1 |       | FLWR  |                             |       | FLWR  |                             |           |
+--------+---------------------------+-------+-------+-----------------------------+-------+-------+-----------------------------+-----------+



Links to listed docs
--------------------

* thesis - `<https://github.com/ongardie/dissertation/blob/master/online.pdf>`__

