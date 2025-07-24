# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is a banking simulation example demonstrating distributed system architecture patterns. It's designed as a stepping stone toward integrating with a Raft consensus system, showing how to build modular, testable banking operations with multiple transport mechanisms.

**Important: This is an educational example, not a production application.** The primary goal is to illustrate Raft integration patterns in the clearest, most readable way possible.

## Development Philosophy

### Code for Reading, Not Production
This codebase prioritizes **clarity and educational value over production robustness**. The code is meant to be read and understood more than it is meant to be run in production environments.

### Minimalist Approach
When adding new code, follow the principle of **absolute necessity**:
- **No logging** unless essential for demonstrating a concept
- **No error handling** beyond what's required for basic functionality  
- **No defensive coding** patterns that obscure the core logic
- **No production concerns** like performance optimization, security hardening, or operational monitoring

### Acceptable Failure
If the code breaks badly when things go wrong, **that's perfectly acceptable**. The goal is to show the happy path of Raft integration as clearly as possible, not to handle every edge case or failure scenario that a production system would need.

### Exception Handling Requirements
When adding exception handling to code, follow these strict guidelines:

**NEVER do this:**
```python
try:
    some_operation()
except Exception as e:
    logger.error(f"Error: {e}")  # USELESS - no context!
    return None
```

**ALWAYS do this instead:**
```python
try:
    some_operation()
except Exception as e:
    logger.error(f"Failed to perform some_operation in ClassName.method_name: {e}")
    logger.error(f"Full traceback: {traceback.format_exc()}")
    raise  # Re-raise unless you have a specific reason to handle it
```

**Key principles:**
- **Don't catch exceptions unless you can do something useful with them**
- **Always include context**: what operation was being attempted, which class/method, what parameters
- **Always include full traceback** using `traceback.format_exc()` or `traceback.print_exc()`
- **This is development code** - users need full debugging information, not sanitized error messages
- **When in doubt, don't catch it** - let it bubble up with full stack trace

## Architecture

### Core Banking Logic
- **Teller** (`src/base/operations.py`): Main banking operations class handling deposits, withdrawals, transfers, customer/account creation, and statement generation
- **BankDatabase** (`src/base/database.py`): SQLite-based persistence layer with full CRUD operations for customers, accounts, transactions, and statements
- **Data Types** (`src/base/datatypes.py`): Strongly-typed data classes for Customer, Account, Transaction, Statement with serialization support

### Abstraction Layers
- **TellerProxyAPI** (`src/base/proxy.py`): Abstract interface defining banking operations, with TellerWrapper providing direct implementation
- **Dispatcher** (`src/base/dispatcher.py`): JSON command processor that routes method calls to the Teller, handles serialization of Decimal types
- **Collector** (`src/base/collector.py`): Client-side abstraction that converts method calls to JSON commands for remote execution

### Transport Implementations
- **AsyncStream** (`src/tx_astream/`): TCP-based RPC using asyncio streams
- **ZeroMQ** (`src/tx_aiozmq/`): ZeroMQ-based RPC using aiozmq library (requires `aiozmq==1.0.0`, `msgpack==1.1.1`)

### Raft Integration Stubs
- **DeckStub** (`src/raft_stubs/stubs.py`): Placeholder for Raft consensus integration, currently implements echo server for raft_message calls
- **RaftServerStub** (`src/raft_stubs/stubs.py`): Server adapter that bridges RPC calls to the DeckStub

## Key Design Patterns

### Command Pattern
Banking operations are abstracted as JSON commands processed by the Dispatcher, enabling remote execution across different transports.

### Layered Architecture
- **Business Logic**: Teller class with pure banking operations
- **Persistence**: BankDatabase with SQLite backend
- **Transport**: Pluggable RPC mechanisms (AsyncStream, ZeroMQ)
- **Protocol**: JSON-based command serialization

### Type Safety
All monetary values use Python's Decimal type with 2-decimal precision, preventing floating-point errors in financial calculations.

## Development Commands

### Running Examples
```bash
# ZeroMQ-based client/server (requires aiozmq installation)
python src/cli/test_zq_stub_server.py  # Server
python src/cli/test_zq_stub_client.py  # Client

# AsyncStream-based client/server  
python src/cli/test_as_stub_server.py  # Server
python src/cli/test_as_stub_client.py  # Client
```

### Testing
```bash
# Install ZeroMQ dependencies for full testing
pip install -r src/tx_aiozmq/requirements.txt

# Run validation tests through different transport layers
python src/cli/validate_teller.py      # Direct validation
python src/cli/validate_collector.py   # Through collector abstraction
```

## Integration Points

### Database Persistence
The BankDatabase creates SQLite tables automatically and handles all persistence. Database file location is configurable (defaults to `/tmp/bank.db`).

### Time Simulation
The Teller class maintains `sim_datetime` for consistent time-based operations, including automatic monthly statement generation when time advances across month boundaries.

### Raft Preparation
The current implementation provides stubs (`DeckStub`, `RaftServerStub`) that demonstrate the interface patterns needed for Raft consensus integration while maintaining a working banking system.

## Performance Benchmarking

### Validator Performance Analysis
- Conducted comprehensive performance testing of validators in `@src/cli`
  - Validated different implementation layers: 
    1. Bare Teller class
    2. Teller wrapped with Collector and Dispatcher
    3. RPC stubs against servers without Raft support
    4. Raft servers and clients
  - Each validator configured to output measurement data to JSON files
  - Ran 200 iterations for each validator using gRPC transport
  - Goal: Analyze performance overhead of each abstraction layer
  - Recommended next steps: Compare JSON measurement files to understand performance implications of additional functionality