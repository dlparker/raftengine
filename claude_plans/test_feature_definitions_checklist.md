# Test Feature Definitions Checklist

This checklist tracks which tests have been upgraded to include feature definitions according to the Raft Feature Identification Methodology. Tests are marked as **complete** (✓) when they have `registry.get_raft_feature()` calls properly integrated.

## Status Summary
- **Total Tests**: 74
- **Tests with Feature Definitions**: 14 (all properly implemented)
- **Tests Remaining**: 60
- **Completion Rate**: 18.9%
- **API Status**: ✓ All existing feature registry calls now use correct API pattern

## Test Files and Methods

### test_class_edges.py (0/4 complete) USES NO RAFT FEATURES
- [NA] `test_class_edges.py::test_bogus_pilot`
- [NA] `test_class_edges.py::test_str_methods`
- [NA] `test_class_edges.py::test_enum_edges`
- [NA] `test_class_edges.py::test_message_ops`

### test_commands_1.py (11/13 complete)
- [x] `test_commands_1.py::test_command_1` ✓
- [x] `test_commands_1.py::test_command_2_leaders_1` ✓
- [x] `test_commands_1.py::test_command_sqlite_1` ✓
- [x] `test_commands_1.py::test_command_2_leaders_2` ✓
- [x] `test_commands_1.py::test_command_2_leaders_3` ✓
- [x] `test_commands_1.py::test_command_after_heal_1` ✓
- [x] `test_commands_1.py::test_command_after_heal_2` ✓
- [x] `test_commands_1.py::test_follower_explodes_in_command` ✓
- [x] `test_commands_1.py::test_leader_explodes_in_command` ✓
- [x] `test_commands_1.py::test_long_catchup` ✓
- [x] `test_commands_1.py::test_full_catchup` ✓
- [ ] `test_commands_1.py::test_follower_run_error`
- [ ] `test_commands_1.py::test_follower_rewrite_1`

### test_dev_tools.py (0/1 complete) USES NO RAFT FEATURES
- [NA] `test_dev_tools.py::test_log_stuff`

### test_elections_1.py (0/7 complete)
- [ ] `test_elections_1.py::test_election_1`
- [ ] `test_elections_1.py::test_election_2`
- [ ] `test_elections_1.py::test_reelection_1`
- [ ] `test_elections_1.py::test_reelection_2`
- [ ] `test_elections_1.py::test_reelection_3`
- [ ] `test_elections_1.py::test_pre_election_1`
- [ ] `test_elections_1.py::test_pre_vote_reject_1`

### test_elections_2.py (0/13 complete)
- [ ] `test_elections_2.py::test_stepwise_election_1`
- [ ] `test_elections_2.py::test_run_to_election_1`
- [ ] `test_elections_2.py::test_election_timeout_1`
- [ ] `test_elections_2.py::test_election_vote_once_1`
- [ ] `test_elections_2.py::test_election_candidate_too_slow_1`
- [ ] `test_elections_2.py::test_election_candidate_log_too_old_1`
- [ ] `test_elections_2.py::test_election_candidate_log_too_old_2`
- [ ] `test_elections_2.py::test_election_candidate_term_too_old_1`
- [ ] `test_elections_2.py::test_failed_first_election_1`
- [ ] `test_elections_2.py::test_failed_first_election_2`
- [ ] `test_elections_2.py::test_power_transfer_1`
- [ ] `test_elections_2.py::test_power_transfer_2`
- [ ] `test_elections_2.py::test_power_transfer_fails_1`

### test_events.py (0/2 complete)
- [ ] `test_events.py::test_event_handlers`
- [ ] `test_events.py::test_message_errors`

### test_log_fiddles.py (0/2 complete)
- [ ] `test_log_fiddles.py::test_empty_log_1`
- [ ] `test_log_fiddles.py::test_empty_log_2`

### test_member_changes.py (0/18 complete)
- [ ] `test_member_changes.py::test_member_change_messages`
- [ ] `test_member_changes.py::test_cluster_config_ops`
- [ ] `test_member_changes.py::test_remove_follower_1`
- [ ] `test_member_changes.py::test_remove_leader_1`
- [ ] `test_member_changes.py::test_add_follower_1`
- [ ] `test_member_changes.py::test_add_follower_2`
- [ ] `test_member_changes.py::test_add_follower_2_rounds_1`
- [ ] `test_member_changes.py::test_add_follower_3_rounds_1`
- [ ] `test_member_changes.py::test_add_follower_too_many_rounds_1`
- [ ] `test_member_changes.py::test_add_follower_round_2_timeout_1`
- [ ] `test_member_changes.py::test_reverse_add_follower_1`
- [ ] `test_member_changes.py::test_reverse_remove_follower_1`
- [ ] `test_member_changes.py::test_reverse_remove_follower_2`
- [ ] `test_member_changes.py::test_reverse_remove_follower_3`
- [ ] `test_member_changes.py::test_add_follower_timeout_1`
- [ ] `test_member_changes.py::test_add_follower_errors_1`
- [ ] `test_member_changes.py::test_remove_candidate_1`
- [ ] `test_member_changes.py::test_update_settings`

### test_msg_edges.py (0/2 complete)
- [ ] `test_msg_edges.py::test_slow_voter`
- [ ] `test_msg_edges.py::test_message_errors`

### test_partition_1.py (0/4 complete)
- [ ] `test_partition_1.py::test_partition_1`
- [ ] `test_partition_1.py::test_partition_2_leader`
- [ ] `test_partition_1.py::test_partition_3_leader`
- [ ] `test_partition_1.py::test_partition_3_follower`

### test_random_code.py (3/3 complete)
- [NA] `test_random_code.py::test_get_deck` USES NO RAFT FEATURES
- [x] `test_random_code.py::test_feature_defs_1` ✓
- [x] `test_random_code.py::test_feature_defs_2` ✓
- [x] `test_random_code.py::test_feature_defs_3` ✓
- [NA] `test_random_code.py::test_feature_defs_4` (Note: This test does not exist)

### test_snapshots.py (0/5 complete)
- [ ] `test_snapshots.py::test_dict_ops`
- [ ] `test_snapshots.py::test_snapshot_1`
- [ ] `test_snapshots.py::test_snapshot_2`
- [ ] `test_snapshots.py::test_snapshot_3`
- [ ] `test_snapshots.py::test_snapshot_4`

### test_timers_1.py (0/4 complete)
- [ ] `test_timers_1.py::test_heartbeat_1`
- [ ] `test_timers_1.py::test_heartbeat_2`
- [ ] `test_timers_1.py::test_lost_leader_1`
- [ ] `test_timers_1.py::test_candidate_timeout_1`

## Priority Order for Feature Definition Implementation

### High Priority (Core Raft Features)
1. **Leader Election Tests** (test_elections_1.py, test_elections_2.py) - 20 tests
2. **Command Processing Tests** (remaining in test_commands_1.py) - 11 tests
3. **Membership Change Tests** (test_member_changes.py) - 18 tests
4. **Network Partition Tests** (test_partition_1.py) - 4 tests

### Medium Priority (Advanced Features)
5. **Snapshot Tests** (test_snapshots.py) - 5 tests
6. **Timer Tests** (test_timers_1.py) - 4 tests
7. **Log Recovery Tests** (test_log_fiddles.py) - 2 tests

### Lower Priority (Edge Cases and System Tests)
8. **Event System Tests** (test_events.py) - 2 tests
9. **Message Edge Cases** (test_msg_edges.py) - 2 tests
10. **Class/API Tests** (test_class_edges.py) - 4 tests
11. **Development Tests** (test_dev_tools.py) - 1 test

## Notes
- Tests marked with ✓ have been confirmed to include `registry.get_raft_feature()` calls
- Tests in test_random_code.py are demonstration/validation tests for the feature system itself
- Priority order is based on core Raft algorithm importance and test coverage impact
- Update this checklist whenever a test is upgraded to include feature definitions