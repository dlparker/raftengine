# gRPC Import Problems and Solutions

This document explains the recurring import issues with generated gRPC code and provides definitive solutions.

## The Problem

Every time we generate gRPC code from `.proto` files, we encounter import failures. The generated files (`banking_pb2.py`, `banking_pb2_grpc.py`) cannot be imported consistently across different execution contexts.

## Root Causes

### 1. Inconsistent Import Patterns
```python
# In rpc_server.py and rpc_client.py (WRONG)
import banking_pb2
import banking_pb2_grpc

# In test_grpc_stub_server.py (ALSO PROBLEMATIC)
import tx_grpc.banking_pb2_grpc as banking_pb2_grpc
```

### 2. Python Module Resolution Context
- When running from `src/cli/`: Python looks for modules relative to `src/`
- When running from `src/tx_grpc/`: Python looks for modules relative to `src/tx_grpc/`
- The generated files are in `src/tx_grpc/` but import expectations vary by execution context

### 3. Generated File Location vs Package Structure
- `generate_grpc.py` creates files in the same directory as the script
- But the files don't follow proper Python package import conventions
- Missing proper package-relative imports

## The Correct Solution

### Option 1: Consistent Absolute Imports (RECOMMENDED)

**Step 1**: Ensure all files use absolute imports from the package root:

```python
# In ALL files (rpc_server.py, rpc_client.py, CLI scripts)
from tx_grpc import banking_pb2, banking_pb2_grpc
```

**Step 2**: Update `tx_grpc/__init__.py` to re-export the generated modules:

```python
# tx_grpc/__init__.py
try:
    from .banking_pb2 import *
    from .banking_pb2_grpc import *
except ImportError:
    print("gRPC generated files not found. Run generate_grpc.py first.")
    print("python src/tx_grpc/generate_grpc.py")
    raise
```

**Step 3**: Ensure all CLI scripts properly setup sys.path:

```python
# Standard pattern for all CLI scripts
from pathlib import Path
import sys

this_dir = Path(__file__).resolve().parent
for parent in this_dir.parents:
    if parent.name == 'src':
        if parent not in sys.path:
            sys.path.insert(0, str(parent))
        break
```

### Option 2: Relative Imports with Proper Package Structure

**Alternative approach** (more complex, not recommended for this project):

```python
# In tx_grpc/rpc_server.py
from . import banking_pb2, banking_pb2_grpc

# But this requires running as a module:
# python -m tx_grpc.rpc_server
```

## Working Example Code

### Corrected rpc_server.py:
```python
import asyncio
import grpc
from concurrent import futures

# Correct import pattern
from tx_grpc import banking_pb2, banking_pb2_grpc

class BankingServicer(banking_pb2_grpc.BankingServiceServicer):
    def __init__(self, raft_server):
        self.raft_server = raft_server
    
    async def SendCommand(self, request, context):
        result = await self.raft_server.run_command(request.command)
        return banking_pb2.CommandResponse(result=result)
    
    async def RaftMessage(self, request, context):
        result = await self.raft_server.raft_message(request.message)
        return banking_pb2.RaftResponse(result=result)
```

### Corrected rpc_client.py:
```python
import asyncio
import grpc

# Correct import pattern
from tx_grpc import banking_pb2, banking_pb2_grpc

class RPCClient:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.channel = None
        self.stub = None
    
    async def connect(self):
        address = f'{self.host}:{self.port}'
        self.channel = grpc.aio.insecure_channel(address)
        self.stub = banking_pb2_grpc.BankingServiceStub(self.channel)
    
    async def send_command(self, command):
        if self.stub is None:
            await self.connect()
        request = banking_pb2.CommandRequest(command=command)
        response = await self.stub.SendCommand(request)
        return response.result
```

### Corrected CLI script pattern:
```python
#!/usr/bin/env python
import asyncio
from pathlib import Path
import sys
import grpc

# Standard sys.path setup
this_dir = Path(__file__).resolve().parent
for parent in this_dir.parents:
    if parent.name == 'src':
        if parent not in sys.path:
            sys.path.insert(0, str(parent))
        break

# Now these imports will work consistently
from tx_grpc.rpc_server import BankingServicer
from tx_grpc import banking_pb2_grpc
from raft_stubs.stubs import DeckStub, RaftServerStub
```

## Implementation Checklist

1. ✅ Generate gRPC code: `python src/tx_grpc/generate_grpc.py`
2. ✅ Update `tx_grpc/__init__.py` with re-exports
3. ✅ Fix all import statements to use `from tx_grpc import ...`
4. ✅ Ensure all CLI scripts have proper sys.path setup
5. ✅ Test from different directories to verify consistency

## Why This Problem Keeps Recurring

1. **Generated code location**: protoc always generates files in the specified output directory
2. **Package structure assumptions**: Python import system expects consistent package structure
3. **Execution context variation**: Running from different directories changes module resolution
4. **Copy-paste patterns**: Previous solutions often work in one context but fail in others

## Prevention for Future gRPC Implementations

1. **Always use absolute imports** from a known package root
2. **Set up proper __init__.py re-exports** for generated modules
3. **Test imports from multiple execution contexts** (CLI directory, package directory, project root)
4. **Document the exact steps** needed after running the code generator
5. **Use consistent sys.path setup patterns** across all entry points

---

*This document should be referenced every time we work with gRPC generated code to avoid repeating these import issues.*