.. _conformance_checklist:

Raft Protocol Conformance Checklist
==================================

This checklist maps raftengine tests to the Raft protocol specification, as defined in Diego Ongaro’s thesis, “Consensus: Bridging Theory and Practice.”

.. list-table:: Conformance Checklist
   :widths: 15 30 30 25
   :header-rows: 1

   * - Section
     - Component
     - Tests
     - Status
   * - 5.2
     - Leader Election
     - :ref:`test_snapshot_4`
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
     - Partial (log consistency covered, needs divergence tests)
   * - 9.6
     - PreVote Extension
     - :ref:`test_snapshot_4`
     - Covered
   * - 8
     - Client Interactions
     - None
     - Pending
   * - 9.7
     - Quorum Check Extension
     - None
     - Pending

Notes
-----

- “Covered” indicates tests validate the component fully.
- “Partial” indicates partial validation (e.g., safety needs more tests for log divergence).
- “Pending” indicates no tests provided yet for the component.
