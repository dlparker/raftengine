"""
pytest configuration for the raftengine tests.

This file is automatically loaded by pytest and provides
shared fixtures and configuration for all tests.
"""
import os
import pytest

# Set ipdb as the default breakpoint() debugger
# This makes breakpoint() use ipdb.set_trace instead of pdb.set_trace
os.environ['PYTHONBREAKPOINT'] = 'ipdb.set_trace'

@pytest.fixture(scope="session", autouse=True)
def configure_breakpoint():
    """
    Automatically configure ipdb as the breakpoint debugger for all tests.
    
    This fixture runs automatically for all tests and ensures that
    breakpoint() uses ipdb.set_trace, providing the same debugging
    experience as the run_tests.sh script.
    
    Usage in tests:
        def test_something():
            breakpoint()  # This will use ipdb instead of pdb
            assert True
    """
    # Ensure the environment variable is set
    os.environ['PYTHONBREAKPOINT'] = 'ipdb.set_trace'
    yield
    # Cleanup after tests (optional)
    pass