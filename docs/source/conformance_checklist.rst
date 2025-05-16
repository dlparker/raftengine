.. _conformance_checklist:

Raft Protocol Conformance Checklist
===================================

.. list-table:: Conformance Checklist
   :widths: 15 30 30 25
   :header-rows: 1

   * - Section
     - Component
     - Tests
     - Status
   * - 5.2
     - Leader Election
     - :ref:`test_snapshot_5`
     - Covered
   * - 5.3
     - Log Replication
     - :ref:`test_snapshot_2`, :ref:`test_snapshot_3`, :ref:`test_snapshot_4`, :ref:`test_snapshot_5`
     - Covered
   * - 6
     - Membership Changes
     - :ref:`test_snapshot_3`
     - Covered
   * - 7
     - Snapshots
     - :ref:`test_snapshot_2`, :ref:`test_snapshot_3`, :ref:`test_snapshot_4`, :ref:`test_snapshot_5`
     - Covered
   * - 5.4
     - Safety Properties
     - :ref:`test_snapshot_2`, :ref:`test_snapshot_3`, :ref:`test_snapshot_4`, :ref:`test_snapshot_5`
     - Partial
   * - 9.6
     - PreVote Extension
     - :ref:`test_snapshot_5`
     - Pending
