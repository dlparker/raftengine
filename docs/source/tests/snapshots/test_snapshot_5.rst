.. _test_snapshot_5:

Test Snapshot 5
===============

Overview
--------

The ``test_snapshot_3`` test, from ``tests/test_snapshots.py``, validates the Raft protocol’s handling of a new node addition, where a snapshot is sent to initialize the node’s state. [Docstring: e.g., Tests snapshot load on new node add].

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
     - Leader sends ``m_c+N-X op=add`` to add a new node, using joint consensus.
   * - 7
     - Snapshots
     - Leader sends ``sn+N-X i-Y`` to the new node, which installs it (``snr+N-X s-True``).
   * - 5.3
     - Log Replication
     - New node receives ``ae+N-X`` to sync post-snapshot.

Key Operations
--------------

- Membership Change: ``m_c+N-X op=add n=N-Y``, ``m_cr+N-X ok-True``.
- Snapshot: ``sn+N-X i-Y``, ``snr+N-X i-Y s-True``.
- Log Replication: ``ae+N-X``, ``ae_reply+N-X ok-True mi-Z``.

.. graphviz:: ../../_static/diagrams/test_snapshot_3.dot
   :caption: State transitions for new node addition and snapshot installation.

Notes
-----

- Verifies Raft’s safety properties (Section 5.4) for membership changes.
- Ensures consistent state for new nodes via snapshots.

.. graphviz:: ../../_static/diagrams/test_snapshot_3.dot
.. seealso::

   - :download:`Test Snapshot 3 Trace Table <../../_static/test_data/test_snapshot_3.csv>`
   - Ongaro’s thesis, `Consensus: Bridging Theory and Practice <https://web.stanford.edu/~ouster/cgi-bin/papers/raft-atc14.pdf>`_.
