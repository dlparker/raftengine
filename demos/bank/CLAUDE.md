# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is a demo application that demonstrates how to integrate the Raft consensus algorithm library into a distributed banking system. The demo progresses through three evolutionary stages: no-raft, raft-prep, and full raft integration, showing developers how to transform a standard client-server application into a distributed consensus system.

## Key Architecture

### Core Components

The banking system is built around a layered architecture:

- **Base Layer** (`src/base/`): Core business logic and data models
  - `datatypes.py`: Banking entities (Customer, Account, Transaction, Statement) and CommandType enum
  - `server.py`: Main banking server implementation with all business operations
  - `client.py`: Banking client that communicates through proxy interfaces  
  - `proxy_api.py`: Abstract interface defining the contract between client and server
  - `database.py`: SQLite-based persistence layer for banking data

- **Transport Abstractions**: Multiple RPC mechanisms demonstrating different approaches
  - **Direct**: In-process calls for understanding core functionality
  - **Indirect**: Proxy pattern with command serialization (raft preparation)
  - **Async Streams**: TCP-based asyncio streams implementation
  - **gRPC**: Protocol buffer-based RPC implementation

### Demo Evolution Stages

1. **No Raft** (`src/no_raft/`): Standard client-server patterns
   - Direct in-process version for understanding core logic
   - Multiple transport implementations (gRPC, async streams)
   - Focus on traditional RPC patterns

2. **Raft Prep** (`src/raft_prep/`): Preparation for consensus integration
   - Command-based architecture using CommandType enum
   - Serialization/deserialization of operations
   - Proxy pattern that simulates raft log replication
   - Demonstrates the "state machine command" pattern essential for Raft

3. **Raft Integration** (`src/raft_bits/`): Full consensus implementation (in development)
   - Integration with the parent raftengine library
   - Distributed consensus for banking operations

### Key Design Patterns

**Command Pattern**: Banking operations are converted to serializable commands (CommandType enum) that can be replicated across a Raft cluster. This is demonstrated in the proxy implementations where method calls become command objects.

**Proxy Pattern**: The ProxyAPI abstraction allows the same client code to work with different transport mechanisms (direct, TCP, gRPC) and different consensus approaches (no-raft vs raft-enabled).

**Async-First Design**: All banking operations are async, supporting both high-concurrency scenarios and integration with async transport layers.

## Development Commands

### Running Tests

```bash
# Run all tests with coverage
pytest

# Run specific test file
pytest tests/test_client.py

# Run with coverage report
pytest --cov=src --cov-report=html
```

### Running Demo Applications

```bash
# Direct in-process demo (simplest to understand)
python src/no_raft/direct/one_process.py

# Async streams client-server demo
python src/no_raft/async_streams/as_server.py  # Terminal 1
python src/no_raft/async_streams/as_client.py  # Terminal 2

# gRPC client-server demo
python src/no_raft/grpc/grpc_server.py  # Terminal 1
python src/no_raft/grpc/grpc_client.py  # Terminal 2

# Interactive CLI (supports multiple transports)
python src/no_raft/interactive/banking_cli.py

# Raft-prep demos (with raft_message capability)
python src/raft_prep/grpc/raft_prep_grpc_server.py      # Terminal 1
python src/raft_prep/grpc/raft_prep_grpc_client.py      # Terminal 2

python src/raft_prep/async_streams/raft_prep_as_server.py   # Terminal 1
python src/raft_prep/async_streams/raft_prep_as_client.py   # Terminal 2
```

### Development Workflow

The recommended approach for understanding and extending this demo:

1. **Start with Direct Mode**: Run `src/no_raft/direct/one_process.py` to understand core banking operations
2. **Examine Transport Layers**: Look at different RPC implementations in `src/no_raft/transports/`
3. **Study Raft Preparation**: Examine `src/raft_prep/` to understand command serialization patterns
4. **Implement New Features**: Add new banking operations by:
   - Adding to CommandType enum in `datatypes.py`
   - Implementing in `server.py`
   - Adding to `client.py` and `proxy_api.py`
   - Testing with direct mode first, then other transports

## Testing Strategy

Tests are organized by component and integration level:
- `test_client.py`: Client-side logic tests
- `test_server.py`: Server-side business logic tests  
- `test_integration_flow.py`: End-to-end workflow tests
- `test_proxy_api.py`: Proxy abstraction tests
- `test_json_serialization.py`: Command serialization tests

The test suite uses pytest with async support and includes coverage reporting configured for 80% minimum coverage.

## Key Implementation Notes

### Command Serialization
The transition from no-raft to raft-prep demonstrates how to convert method calls into serializable commands. The CommandType enum values must exactly match Server method names for the methodcaller pattern to work.

### Database Integration
The BankDatabase class provides a complete SQLite implementation showing how to integrate banking operations with persistent storage, including transaction history and monthly statement generation.

### Transport Flexibility
The ProxyAPI abstraction allows the same banking client code to work with any transport mechanism, making it easy to compare different RPC approaches and migrate between them.

## Important Lessons Learned

### Inheritance vs Direct Implementation

**For Educational Purposes**: The demo shows both inheritance-based raft_prep (extending no_raft components) and direct implementation patterns. The inheritance approach is valuable for learning because it clearly shows "what we're adding for Raft support."

**For Production Applications**: **Avoid inheritance from no_raft components**. Direct implementation is strongly recommended because:

- **Protobuf/gRPC Conflicts**: Different package namespaces (`banking` vs `raft_banking`) cause descriptor pool conflicts
- **Service Endpoint Mismatches**: Inherited clients call wrong gRPC service paths
- **Complex Dependencies**: Import chains become convoluted and hard to debug
- **Maintenance Burden**: Changes to base classes can break raft implementations unexpectedly
- **Production Simplicity**: Once you commit to Raft, you don't need the non-raft version running

### Recommended Production Pattern

```
production_app/
├── core/              # Shared business logic
├── raft_banking/      # Complete Raft implementation
└── docs/
    └── migration_guide/   # How we evolved from basic to raft
```

**Instead of:**
```
app/
├── no_raft/          # Running in production
├── raft_prep/        # Inherits from no_raft (problematic)
└── raft/             # Final version
```

### Implementation Strategy

1. **Start with no_raft** for learning and prototyping
2. **Copy patterns, don't inherit** when building raft version
3. **Keep both for comparison** during development
4. **Archive no_raft** once raft is stable
5. **Extract shared business logic** to common libraries if needed

This approach provides clear learning progression without production complexity.

## Before/After Examples: Inheritance vs Direct Implementation

During development, we initially tried inheritance-based approaches but found they caused several issues. Here are concrete examples showing the problematic inheritance patterns and their improved direct implementations.

### Example 1: Async Streams Transport

**❌ Before (Inheritance-based):**
```python
# raft_prep/transports/async_streams/proxy.py
from src.no_raft.transports.async_streams.proxy import ServerProxy, ASServer, ASClient

class RaftServerProxy(ServerProxy):
    async def raft_message(self, in_message) -> None:
        args = locals()
        del args['self']
        return await self.as_client.do_command("raft_message", args)

class RaftASServer(ASServer):
    pass

def get_astream_client(host: str, port: int):
    as_client = ASClient(host, port)  # Using no_raft class
    proxy = RaftServerProxy(as_client)
    client = RaftClient(proxy)
    # ...
```

**Problems with inheritance approach:**
- Tight coupling to no_raft implementation
- Hidden dependencies and import complexity
- Difficult to debug when issues span inheritance chain
- Unclear which version of methods are being called

**✅ After (Direct implementation):**
```python
# raft_prep/transports/async_streams/proxy.py
import asyncio
from operator import methodcaller
from typing import List, Optional, Dict, Any
from datetime import timedelta, date
from decimal import Decimal

from src.base.client import Client
from src.base.datatypes import Customer, Account, AccountType, CommandType
from src.base.proxy_api import ProxyAPI
from src.base.json_helpers import bank_json_dumps, bank_json_loads

class RaftASClient:
    """Async streams client for Raft-enabled banking operations"""
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.reader = None
        self.writer = None

    async def do_command(self, command_name: CommandType, argsdict: Dict[str, Any]) -> Any:
        # Complete implementation copied from no_raft but standalone
        # ...

class RaftServerProxy(ProxyAPI):
    """Proxy for Raft-enabled banking operations via async streams"""
    def __init__(self, as_client: RaftASClient) -> None:
        self.as_client = as_client
        
    async def create_customer(self, first_name: str, last_name: str, address: str) -> Customer:
        # Direct implementation
        # ...
        
    async def raft_message(self, in_message) -> None:
        args = locals()
        del args['self']
        return await self.as_client.do_command("raft_message", args)
```

**Benefits of direct implementation:**
- Self-contained and easy to understand
- No hidden dependencies
- Clear debugging and error messages
- Explicit control over all functionality

### Example 2: gRPC Server

**❌ Before (Inheritance-based):**
```python
# raft_prep/transports/grpc/server.py
from src.no_raft.transports.grpc.server import BankingServiceImpl

class RaftBankingServiceImpl(BankingServiceImpl):
    def __init__(self, raft_server):
        super().__init__(raft_server)  # Hidden initialization
    
    def RaftMessage(self, request, context):
        # Only implementing the new method
        # All other methods inherited (hidden dependencies)
        # ...
```

**Problems:**
- Method resolution errors (wrong protobuf package)
- "Method not found!" gRPC errors due to service endpoint mismatches
- Difficult to trace which implementation is being called
- Proto package conflicts between no_raft and raft_prep

**✅ After (Direct implementation):**
```python
# raft_prep/transports/grpc/server.py
import asyncio
import grpc
from concurrent import futures
from datetime import datetime, timedelta
from decimal import Decimal

from . import banking_pb2
from . import banking_pb2_grpc
from src.base.datatypes import Customer, Account, AccountType

class RaftBankingServiceImpl(banking_pb2_grpc.BankingServiceServicer):
    """gRPC service implementation for Raft-enabled banking operations"""
    
    def __init__(self, raft_server):
        self.server = raft_server
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
    
    def CreateCustomer(self, request, context):
        """Create a new customer"""
        # Complete implementation visible here
        # ...
    
    def CreateAccount(self, request, context):
        """Create a new account"""
        # Complete implementation visible here
        # ...
    
    def RaftMessage(self, request, context):
        """Handle Raft consensus messages"""
        # New Raft-specific functionality
        # ...
```

**Benefits:**
- All methods explicitly implemented and visible
- No proto package conflicts
- Clear error messages with specific line numbers
- Easy to modify any banking operation for Raft-specific needs

### Key Lessons Learned

1. **Inheritance creates debugging complexity**: When errors occur, it's unclear which class/method is being called
2. **Package conflicts multiply**: Different protobuf packages between inherited and inheriting classes cause runtime errors
3. **Hidden dependencies break**: Changes in base classes unexpectedly break derived classes
4. **Copy-paste is sometimes better**: For educational code, explicit implementation aids understanding

### When to Use Each Approach

**Use inheritance when:**
- Working with stable, well-tested base classes
- The relationship is truly "is-a" (not just "shares-some-code-with")
- You need polymorphism across multiple implementations
- You're in a production environment with established patterns

**Use direct implementation when:**
- Learning or demonstrating concepts
- Base classes are experimental or changing frequently
- You need complete control over the implementation
- Debugging and maintainability are priorities
- The shared code is minimal

This demo now uses direct implementation throughout raft_prep/ to provide clear, self-contained examples that are easy to understand and debug.