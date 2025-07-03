Features in Tests
=================

This document provides a comprehensive mapping between Raft features and the tests that exercise them.

Features That Are Tested
-------------------------

The following table shows features that are explicitly tested (validated) by test cases:

.. list-table:: Features Under Test
   :header-rows: 1
   :widths: 50 50

   * - Feature
     - Tests That Test This Feature
   * - Log Replication: Follower recovers from crash and catches up with leader's log
     - test_commands_1::test_command_1
   * - State Machine Command: Commands sent to candidates return retry response
     - test_commands_1::test_command_1
   * - State Machine Command: Commands with minimal node count
     - test_commands_1::test_command_1
   * - State Machine Command: Request Redirect
     - test_commands_1::test_command_1

Features That Are Used (But Not Tested)
----------------------------------------

The following table shows features that are used by tests to set up conditions but are not the primary focus of testing:

.. list-table:: Features Used by Tests
   :header-rows: 1
   :widths: 50 50

   * - Feature
     - Tests That Use This Feature
   * - Leader Election: All Yes Votes with Pre-Vote
     - test_commands_1::test_command_1
   * - Log Replication: Leader sends empty AppendEntries as heartbeats to maintain authority
     - test_commands_1::test_command_1
   * - Log Replication: Leader replicates log entries to followers using AppendEntries
     - test_commands_1::test_command_1
   * - State Machine Command: All In Sync
     - test_commands_1::test_command_1