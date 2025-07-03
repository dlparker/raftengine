
Command Tests
=============

This section documents tests from ``tests/test_commands_1.py`` that test scenarios where a client program requests the cluster to perform a command implemented by the application's state machine.

These tests cover:

- Basic command processing with detailed control
- Command redirection and retry behaviors
- Error handling during command execution  
- Follower crash recovery and catch-up
- Command processing with SQLite log storage

.. toctree::
   :maxdepth: 1

   test_command_1: Basic command processing with detailed control <test_command_1>
   test_command_2_leaders_1: Multiple leaders scenario handling <test_command_2_leaders_1>
   test_command_2_leaders_2: Multiple leaders scenario handling <test_command_2_leaders_2>
   test_command_2_leaders_3: Partitioning makes two leaders, old resigns on heal, redirect <test_command_2_leaders_3>
   test_command_after_heal_1: Command processing after partition healing <test_command_after_heal_1>
   test_command_after_heal_2: Command processing after partition healing <test_command_after_heal_2>
   test_command_sqlite_1: Command processing with SQLite log storage <test_command_sqlite_1>
   test_follower_explodes_in_command: Follower error handling during commands <test_follower_explodes_in_command>
   test_follower_rewrite_1: Follower log rewrite scenarios <test_follower_rewrite_1>
   test_follower_run_error: Follower runtime error handling <test_follower_run_error>
   test_full_catchup: Complete follower catch-up after disconnect <test_full_catchup>
   test_leader_explodes_in_command: Leader error handling during commands <test_leader_explodes_in_command>
   test_long_catchup: Extended follower catch-up scenarios <test_long_catchup>
