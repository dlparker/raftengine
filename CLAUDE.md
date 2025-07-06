# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is a Python implementation of a Raft consensus algorithm library designed to be integrated into distributed systems. The library is designed to be modular, allowing users to supply their own message transport and log storage implementations.

## Key Architecture

### Core Components

- **Deck** (`raftengine/deck/deck.py`): Main entry point and control center for the Raft engine
- **PilotAPI** (`raftengine/api/pilot_api.py`): User-supplied interface for message transport and log storage
- **DeckAPI** (`raftengine/api/deck_api.py`): Main API interface for the Raft engine
- **Roles** (`raftengine/roles/`): Implementation of Raft roles (Leader, Follower, Candidate)
- **Messages** (`raftengine/messages/`): Raft protocol message types (RequestVote, AppendEntries, etc.)

### API Layer

- **LogAPI** (`raftengine/api/log_api.py`): Interface for persistent log storage
- **SnapshotAPI** (`raftengine/api/snapshot_api.py`): Interface for snapshot management
- **Events** (`raftengine/api/events.py`): Event handling system
- **Types** (`raftengine/api/types.py`): Core data types and enums

### Development Tools

- **Trace Tools** (`dev_tools/`): Comprehensive test tracing and visualization system
- **Feature Registry** (`dev_tools/features.py`): Feature mapping and test organization
- **Network Simulation** (`dev_tools/network_sim.py`): Network behavior simulation for testing

## Development Commands

### Running Tests

```bash
# Run all tests with coverage
./run_tests.sh

# Run specific test file
./run_tests.sh tests/test_elections_1.py

# Run specific test method
./run_tests.sh tests/test_elections_1.py::TestElections1::test_election_1
```


```bash
# Run tests with coverage only of dev_tools sources, to identify dead code in dev_tools
./test_tools.sh

### Building Documentation

```bash
# Build all documentation from test traces
python dev_tools/build_docs.py


### Working with Test Traces

The project has an extensive test tracing system that captures detailed execution traces:

```bash
# Generate trace outputs in multiple formats (JSON, CSV, Org, RST, PlantUML)
python dev_tools/build_docs.py

# Create PDF visualizations of traces
python dev_tools/make_trace_pdf.py
```

## Test Organization

Tests are organized by functional areas:
- `test_elections_1.py`, `test_elections_2.py`: Leader election scenarios
- `test_commands_1.py`: Command processing and log replication
- `test_member_changes.py`: Cluster membership changes
- `test_partition_1.py`: Network partition scenarios
- `test_snapshots.py`: Snapshot creation and transfer
- `test_timers_1.py`: Timeout and heartbeat scenarios

## Key Design Patterns

### Message-Based Architecture
The library uses asynchronous message passing rather than RPC, allowing integration with various transport mechanisms (message queues, HTTP, etc.).

### Pluggable Storage
Users provide their own LogAPI implementation, enabling integration with existing database systems and transactional operations.

### Extensive Tracing
All tests generate detailed execution traces in multiple formats for debugging and documentation purposes.

### Event-Driven Design
The system uses an event-driven architecture with configurable event handlers for monitoring and debugging.

## Working with the Codebase

### Adding New Features
1. Implement core logic in appropriate module (`roles/`, `messages/`, `deck/`)
2. Add corresponding API interfaces if needed
3. Create comprehensive tests with trace generation
4. Update documentation using the trace system

### Debugging Issues
1. Use the trace system to capture detailed execution logs
2. Generate visual representations using PlantUML output
3. Use the extensive logging and event system for runtime debugging

### Testing Patterns
- Tests use a simulation framework that controls timing and message delivery
- Network partitions and failures are simulated deterministically
- All scenarios generate reproducible traces for analysis