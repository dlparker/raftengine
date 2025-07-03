Timer and Timeout Tests
=======================

This section documents tests from ``tests/test_timers_1.py`` that test timer-based behaviors including election timeouts, heartbeats, and leader failure detection.

These tests cover:

- Election timeout handling
- Heartbeat mechanisms
- Leader failure detection
- Candidate timeout scenarios
- Timer-driven state transitions

.. toctree::
   :maxdepth: 1

   test_candidate_timeout_1: Candidate election timeout handling <test_candidate_timeout_1>
   test_heartbeat_1: Basic heartbeat mechanism <test_heartbeat_1>
   test_heartbeat_2: Advanced heartbeat scenarios <test_heartbeat_2>
   test_lost_leader_1: Leader loss detection and recovery <test_lost_leader_1>