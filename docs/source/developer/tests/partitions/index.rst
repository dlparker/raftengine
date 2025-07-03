Network Partition Tests
=======================

This section documents tests from ``tests/test_partition_1.py`` that test network partition scenarios and the cluster's behavior when nodes become isolated or reconnected.

These tests cover:

- Basic network partitioning
- Leader isolation scenarios
- Follower isolation scenarios
- Partition recovery and healing
- Split-brain prevention
- Majority/minority partition behavior

.. toctree::
   :maxdepth: 1

   test_partition_1: Basic network partition scenarios <test_partition_1>
   test_partition_2_leader: Leader node partition scenarios <test_partition_2_leader>
   test_partition_3_follower: Follower node partition scenarios <test_partition_3_follower>
   test_partition_3_leader: Three-node leader partition scenarios <test_partition_3_leader>