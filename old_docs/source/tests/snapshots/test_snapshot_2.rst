.. _test_snapshot_2:

Test Snapshot 2
===============

Overview
--------

The ``test_snapshot_2`` test, from ``tests/test_snapshots.py``, validates the Raft protocol’s snapshot installation for a lagging follower. The test simulates a follower whose log is behind the leader’s snapshot index, requiring a snapshot to catch up.

Raft Protocol Mapping
---------------------

.. list-table:: Raft Protocol Components Tested
   :widths: 20 40 40
   :header-rows: 1

   * - Section
     - Component
     - Test Behavior
   * - 7
     - Snapshots
     - Leader sends ``sn+N-2 i=90 t=1`` to lagging follower N-2, which installs it (``snr+N-2 s=True``).
   * - 5.3
     - Log Replication
     - Follower N-2 receives ``ae+N-2 i=91 t=1`` post-snapshot, replying ``ae_reply+N-2 ok=True mi=91``.

Key Operations
--------------

- Snapshot: ``sn+N-2 i=90 t=1``, ``snr+N-2 i=90 s=True`` (installs snapshot at index 90, term 1).
- Log Replication: ``ae+N-2 i=91 t=1``, ``ae_reply+N-2 ok=True mi=91`` (replicates log entries post-snapshot).

.. graphviz:: ../../_static/diagrams/test_snapshot_2.dot
   :caption: State transitions for snapshot installation on lagging follower

.. _test_snapshot_2_csv:

  - :download:`Test Snapshot 2 Trace Table <../../_static/test_data/test_snapshot_2.csv>`

Notes
-----

- Ensures snapshot installation for followers lagging behind the leader’s log (Section 7).
- Validates post-snapshot log replication consistency (Section 5.3).

.. seealso::

   - :ref:`snapshot_process`
   - Ongaro’s thesis, `Consensus: Bridging Theory and Practice <https://web.stanford.edu/~ouster/cgi-bin/papers/raft-atc14.pdf>`_.
