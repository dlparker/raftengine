
Snapshot Tests
==============

This section documents tests from ``tests/test_snapshots.py``, focusing on Raft’s log compaction and snapshot mechanisms.

.. list-table:: Snapshot Test Descriptions
   :widths: 30 70
   :header-rows: 1

   * - Test
     - Description
   * - :ref:`test_snapshot_2`
     - [Docstring: e.g., Tests snapshot recovery after partition].
   * - :ref:`test_snapshot_3`
     - Tests snapshot installation for a new node added to the cluster.
   * - :ref:`test_snapshot_4`
     - Tests snapshot installation for a slow follower
     

.. toctree::
   :maxdepth: 1

   test_snapshot_4
