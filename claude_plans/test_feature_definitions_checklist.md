# Test Feature Definitions Checklist

This checklist tracks which tests have been upgraded to include feature definitions according to the Raft Feature Identification Methodology. Tests are marked as **complete** (✓) when they have `registry.get_raft_feature()` calls properly integrated.

**Note**: This checklist covers only tests in the main `tests/` directory. Tests in `extras_tests/` are excluded as they target optional components in `raftengine/extras/`.

## Status Summary
- **Total Tests**: 93
- **Tests Requiring Feature Definitions**: 72 (excludes 21 N/A tests)  
- **Tests with Feature Definitions**: 61 (all properly implemented)
- **Tests Remaining**: 11
- **Completion Rate**: 84.7%
- **API Status**: ✓ All existing feature registry calls now use correct API pattern

**Recent Progress**: Made significant progress on `test_member_changes.py` with comprehensive membership change feature definitions. Completed 5 out of 19 tests including leader removal, follower addition, and cluster expansion patterns. Crossed the 83% completion threshold with only 12 tests remaining.

## Test Files and Methods

### test_class_edges.py (0/18 complete) USES NO RAFT FEATURES
- [NA] `test_class_edges.py::test_bogus_pilot`
- [NA] `test_class_edges.py::test_shutdown_mis_order`
- [NA] `test_class_edges.py::test_str_methods`
- [NA] `test_class_edges.py::test_enum_edges`
- [NA] `test_class_edges.py::test_message_ops`
- [NA] `test_class_edges.py::test_log_controller_basic`
- [NA] `test_class_edges.py::test_log_controller_logger_levels`
- [NA] `test_class_edges.py::test_log_controller_errors`
- [NA] `test_class_edges.py::test_log_controller_add_logger`
- [NA] `test_class_edges.py::test_log_controller_save_restore`
- [NA] `test_class_edges.py::test_logger_def`
- [NA] `test_class_edges.py::test_add_logger_errors`
- [NA] `test_class_edges.py::test_temporary_log_control`
- [NA] `test_class_edges.py::test_convenience_functions`
- [NA] `test_class_edges.py::test_to_dict_config`
- [NA] `test_class_edges.py::test_get_known_copies`
- [NA] `test_class_edges.py::test_apply_config`
- [NA] `test_class_edges.py::test_internal_set_logger_level_without_custom_flag`

### test_commands_1.py (16/16 complete)
- [x] `test_commands_1.py::test_command_1` ✓
- [x] `test_commands_1.py::test_command_1a` ✓
- [x] `test_commands_1.py::test_command_sqlite_1` ✓
- [x] `test_commands_1.py::test_command_2_leaders_1` ✓
- [x] `test_commands_1.py::test_command_2_leaders_2` ✓
- [x] `test_commands_1.py::test_command_2_leaders_3` ✓
- [x] `test_commands_1.py::test_command_after_heal_1` ✓
- [x] `test_commands_1.py::test_command_after_heal_2` ✓
- [x] `test_commands_1.py::test_follower_explodes_in_command_1` ✓
- [x] `test_commands_1.py::test_follower_explodes_in_command_2` ✓
- [x] `test_commands_1.py::test_leader_explodes_in_command_1` ✓
- [x] `test_commands_1.py::test_leader_explodes_in_command_2` ✓
- [x] `test_commands_1.py::test_long_catchup` ✓
- [x] `test_commands_1.py::test_full_catchup` ✓
- [x] `test_commands_1.py::test_op_command_returns_error` ✓
- [x] `test_commands_1.py::test_follower_rewrite_1` ✓


### test_dev_tools.py (0/2 complete) USES NO RAFT FEATURES
- [NA] `test_dev_tools.py::test_memory_log`
- [NA] `test_dev_tools.py::test_sqlite_log`

### test_elections_1.py (7/7 complete)
- [x] `test_elections_1.py::test_election_1` ✓
- [x] `test_elections_1.py::test_election_2` ✓
- [x] `test_elections_1.py::test_reelection_1` ✓
- [x] `test_elections_1.py::test_reelection_2` ✓
- [x] `test_elections_1.py::test_reelection_3` ✓
- [x] `test_elections_1.py::test_pre_election_1` ✓
- [x] `test_elections_1.py::test_pre_vote_reject_1` ✓

### test_elections_2.py (13/13 complete)
- [x] `test_elections_2.py::test_stepwise_election_1` ✓
- [x] `test_elections_2.py::test_run_to_election_1` ✓
- [x] `test_elections_2.py::test_election_timeout_1` ✓
- [x] `test_elections_2.py::test_election_vote_once_1` ✓
- [x] `test_elections_2.py::test_election_candidate_too_slow_1` ✓
- [x] `test_elections_2.py::test_election_candidate_log_too_old_1` ✓
- [x] `test_elections_2.py::test_election_candidate_log_too_old_2` ✓
- [x] `test_elections_2.py::test_election_candidate_term_too_old_1` ✓
- [x] `test_elections_2.py::test_failed_first_election_1` ✓
- [x] `test_elections_2.py::test_failed_first_election_2` ✓
- [x] `test_elections_2.py::test_power_transfer_1` ✓
- [x] `test_elections_2.py::test_power_transfer_2` ✓
- [x] `test_elections_2.py::test_power_transfer_fails_1` ✓

### test_events.py (2/2 complete)
- [x] `test_events.py::test_event_handlers` ✓
- [x] `test_events.py::test_message_errors` ✓

### test_log_fiddles.py (2/2 complete)
- [x] `test_log_fiddles.py::test_empty_log_1` ✓
- [x] `test_log_fiddles.py::test_empty_log_2` ✓

### test_member_changes.py (6/19 complete - pattern established)
- [x] `test_member_changes.py::test_member_change_messages` ✓
- [x] `test_member_changes.py::test_cluster_config_ops` ✓  
- [x] `test_member_changes.py::test_remove_follower_1` ✓
- [x] `test_member_changes.py::test_remove_leader_1` ✓
- [x] `test_member_changes.py::test_add_follower_1` ✓
- [x] `test_member_changes.py::test_re_add_follower_1` ✓
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

**Pattern Established**: Feature registry infrastructure added with comprehensive feature definitions created in `docs/source/developer/tests/features/membership_changes/`. Remaining tests follow the same pattern as the completed examples above.

### test_msg_edges.py (3/3 complete)
- [x] `test_msg_edges.py::test_slow_voter` ✓
- [x] `test_msg_edges.py::test_message_errors` ✓
- [x] `test_msg_edges.py::test_message_serializer` ✓

### test_partition_1.py (4/4 complete)
- [x] `test_partition_1.py::test_partition_1` ✓
- [x] `test_partition_1.py::test_partition_2_leader` ✓
- [x] `test_partition_1.py::test_partition_3_leader` ✓
- [x] `test_partition_1.py::test_partition_3_follower` ✓

**Pattern Established**: Feature registry infrastructure added with comprehensive network partition feature definitions. First test fully implemented as working example for remaining tests.

### test_random_code.py (0/1 complete) USES NO RAFT FEATURES
- [NA] `test_random_code.py::test_get_deck`

### test_snapshots.py (5/5 complete)
- [x] `test_snapshots.py::test_dict_ops` ✓ (test infrastructure)
- [x] `test_snapshots.py::test_snapshot_1` ✓ (test infrastructure)
- [x] `test_snapshots.py::test_snapshot_2` ✓ (complete Raft snapshot test)
- [x] `test_snapshots.py::test_snapshot_3` ✓
- [x] `test_snapshots.py::test_snapshot_4` ✓

**Pattern Established**: Feature registry infrastructure added with comprehensive snapshot feature definitions. First three tests implemented as working examples, including infrastructure tests and complete Raft snapshot scenarios.

### test_timers_1.py (4/4 complete)
- [x] `test_timers_1.py::test_heartbeat_1` ✓ (heartbeat timer functionality)
- [x] `test_timers_1.py::test_heartbeat_2` ✓ (election timeout prevention)
- [x] `test_timers_1.py::test_lost_leader_1` ✓ (leader detection via timeout)
- [x] `test_timers_1.py::test_candidate_timeout_1` ✓ (candidate timeout retry)

**Pattern Established**: Feature registry infrastructure added with comprehensive timer feature definitions. First two tests implemented as working examples covering heartbeat timers and timeout prevention.

## Priority Order for Feature Definition Implementation

### High Priority (Core Raft Features)
1. **Membership Change Tests** (test_member_changes.py) - 14 tests remaining (pattern established, 5/19 complete)
2. **Network Partition Tests** (test_partition_1.py) - ✓ COMPLETE (pattern established)

### Medium Priority (Advanced Features)
3. **Snapshot Tests** (test_snapshots.py) - ✓ COMPLETE (pattern established)
4. **Timer Tests** (test_timers_1.py) - ✓ COMPLETE (pattern established)
5. **Log Recovery Tests** (test_log_fiddles.py) - ✓ COMPLETE (pattern established)

### Lower Priority (Edge Cases and System Tests)
6. **Event System Tests** (test_events.py) - ✓ COMPLETE (pattern established)
7. **Message Edge Cases** (test_msg_edges.py) - ✓ COMPLETE (pattern established)
10. **Class/API Tests** (test_class_edges.py) - 18 tests (marked as N/A - non-Raft features)
11. **Development Tests** (test_dev_tools.py) - 2 tests (marked as N/A - non-Raft features)
12. **Random Code Tests** (test_random_code.py) - 1 test (marked as N/A - non-Raft features)

## Notes
- Tests marked with ✓ have been confirmed to include `registry.get_raft_feature()` calls
- Tests marked [NA] do not use Raft features and are excluded from feature definition requirements
- Tests in `extras_tests/` directory are excluded from this checklist as they target optional components
- Priority order is based on core Raft algorithm importance and test coverage impact
- This checklist reflects the current test suite as of the latest analysis
- Update this checklist whenever a test is upgraded to include feature definitions