# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is a banking simulation demo application that serves as a proof-of-concept for integrating with a Raft consensus library. The demo implements a layered architecture that mimics how client requests would be converted to state machine commands in a distributed system.

## Architecture

The application follows a four-layer pattern designed to simulate distributed system operations:

### Core Components

- **Client** (`client.py`): High-level interface that applications would use
- **ServerProxy** (`proxy.py`): Converts method calls to serializable commands with arguments
- **ServerWrapper** (`proxy.py`): Deserializes commands back to method calls on the server
- **Server** (`server.py`): Actual business logic implementation for banking operations

### Data Types

- **Customer** (`datatypes.py`): Customer record with ID, name, address, and account list
- **Account** (`datatypes.py`): Account record with ID, type, customer reference, and balance
- **AccountType** (`datatypes.py`): Enum for account types (SAVINGS, CHECKING)
- **CommandType** (`proxy.py`): Enum for serializable command types

### Request Flow

1. Client calls method on ServerProxy
2. ServerProxy converts method call to CommandType + arguments dictionary
3. ServerWrapper receives command and converts back to method call on Server
4. Server executes business logic and returns result

## Banking Operations

The server implements these banking operations:
- `create_customer()` - Create new customer record
- `create_account()` - Create account for existing customer
- `deposit()` / `withdraw()` - Modify account balance
- `transfer()` - Move money between accounts
- `cash_check()` - Withdraw via check
- `list_accounts()` - Get all accounts
- `get_accounts()` - Get customer's accounts
- `list_statements()` - Get account history (placeholder)
- `advance_time()` - Advance simulation time

## Current Implementation Status

- **Complete**: `create_customer()` method fully implemented across all layers
- **Incomplete**: All other banking operations have placeholder implementations
- **Server**: Most business logic implemented but needs database integration
- **Client/Proxy**: Only `create_customer()` method implemented

## Development Commands

### Running the Demo

```bash
python t.py
```

This runs a basic test that creates a customer through the full proxy chain.

## Next Development Steps

According to `next_task.md`, the planned improvements include:
1. Add datetime tracking to Customer and Account records
2. Create Transaction dataclass for audit trail
3. Implement SQLite database storage
4. Complete remaining method implementations in Client and ServerProxy layers

## Design Patterns

### Command Pattern
The proxy layer implements a command pattern where method calls are converted to serializable command objects, enabling the system to replicate operations across distributed nodes.

### Async Architecture
All operations are async to support non-blocking I/O operations that would be required in a distributed system.

### Simulation Time
The server maintains `sim_datetime` for controlled time progression in testing scenarios.