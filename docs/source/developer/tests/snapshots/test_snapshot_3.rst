.. _test_snapshot_3:

Test Snapshot 3
===============

Overview
--------

The ``test_snapshot_3`` test, from ``tests/test_snapshots.py``, validates the Raft protocol’s handling of a new node addition, where a snapshot is sent to initialize the node’s state. The test simulates a cluster where a new node is added via a membership change, requiring a snapshot to bring it up to date with the leader’s log.

Raft Protocol Mapping
---------------------

.. list-table:: Raft Protocol Components Tested
   :widths: 20 40 40
   :header-rows: 1

   * - Section
     - Component
     - Test Behavior
   * - 6
     - Membership Changes
     - Leader sends ``m_c+N-3 op=add`` to add node N-3, using joint consensus.
   * - 7
     - Snapshots
     - Leader sends ``sn+N-3 i=100 t=2`` to node N-3, which installs it (``snr+N-3 s=True``).
   * - 5.3
     - Log Replication
     - Node N-3 receives ``ae+N-3 i=101 t=2`` to sync post-snapshot, replying ``ae_reply+N-3 ok=True mi=101``.

Key Operations
--------------

- Membership Change: ``m_c+N-3 op=add n=N-3``, ``m_cr+N-3 ok=True`` (adds node N-3 to cluster).
- Snapshot: ``sn+N-3 i=100 t=2``, ``snr+N-3 i=100 s=True`` (installs snapshot at index 100, term 2).
- Log Replication: ``nae+N-3 i=101 t=2``, ``ae_reply+N-3 ok=True mi=101`` (replicates log entries post-snapshot).

.. graphviz:: /_static/diagrams/test_snapshot_3.dot
   :caption: State transitions for new node addition and snapshot installation

.. _test_snapshot_3_csv:

  :download:`Test Snapshot 3 Trace Table </_static/test_data/test_snapshot_3.csv>`

Notes
-----

- Verifies Raft’s joint consensus for safe membership changes (Section 6).
- Ensures snapshot installation consistency for new nodes (Section 7).
- Validates post-snapshot log replication (Section 5.3).

.. seealso::

   - :ref: `snapshot_process`
   - Ongaro’s thesis, `Consensus: Bridging Theory and Practice <https://web.stanford.edu/~ouster/cgi-bin/papers/raft-atc14.pdf>`_.

