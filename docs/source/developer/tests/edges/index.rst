Edge Case Tests
===============

This section documents tests from ``tests/test_class_edges.py`` and ``tests/test_msg_edges.py`` that test edge cases, error conditions, and boundary scenarios in the Raft implementation.

These tests cover:

- Invalid pilot implementations
- Message handling edge cases
- Slow voter scenarios
- Error recovery mechanisms
- Boundary condition handling

.. toctree::
   :maxdepth: 1

   test_bogus_pilot: Invalid pilot implementation handling <test_bogus_pilot>
   test_message_errors: Message error handling scenarios <test_message_errors>
   test_slow_voter: Slow voter response handling <test_slow_voter>