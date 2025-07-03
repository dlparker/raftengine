Election Tests
==============

This section documents tests from ``tests/test_elections_1.py`` and ``tests/test_elections_2.py`` that test leader election behaviors in the Raft consensus algorithm.

These tests cover:

- Basic leader election scenarios
- Pre-vote election optimization
- Election timeouts and retries
- Vote rejection due to log inconsistencies
- Power transfer mechanisms
- Election edge cases and failure scenarios

.. toctree::
   :maxdepth: 1

   test_election_1: Basic leader election process <test_election_1>
   test_election_2: Leader election process <test_election_2>
   test_election_candidate_log_too_old_1: Vote rejection due to outdated candidate log <test_election_candidate_log_too_old_1>
   test_election_candidate_log_too_old_2: Vote rejection due to outdated candidate log <test_election_candidate_log_too_old_2>
   test_election_candidate_term_too_old_1: Vote rejection due to outdated candidate term <test_election_candidate_term_too_old_1>
   test_election_candidate_too_slow_1: Slow candidate election handling <test_election_candidate_too_slow_1>
   test_election_timeout_1: Election timeout scenarios <test_election_timeout_1>
   test_election_vote_once_1: Single vote per term validation <test_election_vote_once_1>
   test_failed_first_election_1: Recovery from failed initial election <test_failed_first_election_1>
   test_failed_first_election_2: Recovery from failed initial election <test_failed_first_election_2>
   test_power_transfer_1: Leadership power transfer mechanism <test_power_transfer_1>
   test_power_transfer_2: Leadership power transfer mechanism <test_power_transfer_2>
   test_power_transfer_fails_1: Failed power transfer scenarios <test_power_transfer_fails_1>
   test_pre_election_1: Pre-vote election optimization <test_pre_election_1>
   test_pre_vote_reject_1: Pre-vote rejection scenarios <test_pre_vote_reject_1>
   test_reelection_1: Leader re-election scenarios <test_reelection_1>
   test_reelection_2: Leader re-election scenarios <test_reelection_2>
   test_reelection_3: Leader re-election scenarios <test_reelection_3>
   test_run_to_election_1: Transition to election state <test_run_to_election_1>
   test_stepwise_election_1: Step-by-step election process <test_stepwise_election_1>