Membership Change Tests
=======================

This section documents tests from ``tests/test_member_changes.py`` that test cluster membership changes including adding and removing nodes from the Raft cluster.

These tests cover:

- Adding followers to the cluster
- Removing followers from the cluster
- Leader removal scenarios
- Multi-round membership changes
- Membership change timeouts and errors
- Reverse membership operations
- Configuration update mechanisms

.. toctree::
   :maxdepth: 1

   test_add_follower_1: Basic follower addition <test_add_follower_1>
   test_add_follower_2: Follower addition scenarios <test_add_follower_2>
   test_add_follower_2_rounds_1: Multi-round follower addition <test_add_follower_2_rounds_1>
   test_add_follower_3_rounds_1: Three-round follower addition <test_add_follower_3_rounds_1>
   test_add_follower_errors_1: Follower addition error handling <test_add_follower_errors_1>
   test_add_follower_round_2_timeout_1: Follower addition timeout in round 2 <test_add_follower_round_2_timeout_1>
   test_add_follower_timeout_1: Follower addition timeout scenarios <test_add_follower_timeout_1>
   test_add_follower_too_many_rounds_1: Excessive rounds in follower addition <test_add_follower_too_many_rounds_1>
   test_member_change_messages: Membership change message handling <test_member_change_messages>
   test_remove_candidate_1: Candidate node removal <test_remove_candidate_1>
   test_remove_follower_1: Basic follower removal <test_remove_follower_1>
   test_remove_leader_1: Leader node removal <test_remove_leader_1>
   test_reverse_add_follower_1: Reverse follower addition operation <test_reverse_add_follower_1>
   test_reverse_remove_follower_1: Reverse follower removal operation <test_reverse_remove_follower_1>
   test_reverse_remove_follower_2: Reverse follower removal operation <test_reverse_remove_follower_2>
   test_reverse_remove_follower_3: Reverse follower removal operation <test_reverse_remove_follower_3>
   test_update_settings: Cluster settings update mechanisms <test_update_settings>