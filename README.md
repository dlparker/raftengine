# RaftEngine

A Python implementation of the Raft consensus algorithm for distributed systems.

[![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Overview

RaftEngine is a modular Python library that implements the Raft consensus algorithm, designed to be integrated into distributed systems. The library provides a clean separation between the core Raft logic and the user-supplied transport and storage implementations, making it flexible and adaptable to various deployment scenarios.

### Key Features

- **Modular Architecture**: Clean separation between Raft logic and transport/storage
- **Pluggable Storage**: Integrate with any database or storage system via LogAPI
- **Flexible Transport**: Support any message transport mechanism (HTTP, gRPC, message queues, etc.)
- **Comprehensive Testing**: Extensive test suite with detailed execution tracing
- **Pure Python**: No external dependencies beyond the Python standard library
- **Async-First**: Built on asyncio for high-performance concurrent operations

### Core Components

- **DeckAPI/Deck**: Main entry point and control center for the Raft engine
- **PilotAPI**: User-supplied interface for message transport and log storage  
- **LogAPI**: Interface for persistent log storage
- **Configuration**: Classes for cluster and local server setup
- **Event System**: Comprehensive event handling for monitoring and debugging

## Installation

### From PyPI (recommended)

```bash
pip install raftengine
```

### From Source

```bash
git clone https://github.com/yourusername/raftengine.git
cd raftengine
pip install -e .
```

### Development Installation

```bash
git clone https://github.com/yourusername/raftengine.git
cd raftengine
pip install -e ".[dev]"
```

## Quick Start

Here's a minimal example of how to use RaftEngine:

```python
import asyncio
from raftengine import Deck, LocalConfig, ClusterInitConfig, PilotAPI, LogAPI

# 1. Implement the PilotAPI interface
class MyPilot(PilotAPI):
    def __init__(self, log_api):
        self.log_api = log_api
    
    def get_log(self):
        return self.log_api
    
    async def send_message(self, target_uri, message):
        # Implement message sending to other nodes
        pass
    
    async def send_response(self, target_uri, message):
        # Implement response sending to other nodes
        pass
    
    async def process_command(self, command):
        # Implement command processing for your application
        return {"status": "ok", "result": "processed"}

# 2. Implement the LogAPI interface
class MyLog(LogAPI):
    def __init__(self):
        self.records = []
    
    async def append_record(self, record):
        self.records.append(record)
    
    async def get_records(self, start_index=0, limit=None):
        # Return log records for replication
        pass
    
    # ... implement other required methods

# 3. Set up configuration
local_config = LocalConfig(
    working_dir="/tmp/raft",
    uri="node1"
)

cluster_config = ClusterInitConfig(
    uris=["node1", "node2", "node3"]
)

# 4. Create and start the Raft engine
async def main():
    log = MyLog()
    pilot = MyPilot(log)
    
    deck = Deck(cluster_config, local_config, pilot)
    await deck.start()
    
    # Process commands through the Raft cluster
    result = await deck.run_command({"action": "set", "key": "foo", "value": "bar"})
    print(f"Command result: {result}")

if __name__ == "__main__":
    asyncio.run(main())
```

## Architecture

### Message-Based Design

RaftEngine uses asynchronous message passing rather than RPC, allowing integration with various transport mechanisms:

- HTTP/HTTPS with REST APIs
- gRPC with protocol buffers
- Message queues (RabbitMQ, Apache Kafka, etc.)
- WebSockets for real-time communication
- Custom TCP/UDP protocols

### Pluggable Storage

The LogAPI interface allows integration with any storage system:

- SQL databases (PostgreSQL, MySQL, SQLite)
- NoSQL databases (MongoDB, CouchDB, etc.)
- Key-value stores (Redis, etcd, etc.)
- Custom storage solutions

### Event-Driven Architecture

The library uses events for monitoring and debugging:

```python
from raftengine import EventType, EventHandler

class MyEventHandler(EventHandler):
    async def handle_event(self, event_type, event_data):
        if event_type == EventType.LEADER_ELECTED:
            print(f"New leader elected: {event_data['leader_uri']}")
        elif event_type == EventType.COMMAND_COMMITTED:
            print(f"Command committed: {event_data['command']}")

# Register event handler
deck.add_event_handler(MyEventHandler())
```

## Configuration

### LocalConfig

```python
from raftengine import LocalConfig

config = LocalConfig(
    working_dir="/path/to/raft/data",
    uri="node1",
    record_message_problems=True  # Enable debugging
)
```

### ClusterInitConfig

```python
from raftengine import ClusterInitConfig

config = ClusterInitConfig(
    uris=["node1", "node2", "node3"],
    # Additional cluster configuration options
)
```

## Testing

Run the test suite:

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=raftengine

# Run specific test file
pytest tests/test_elections.py

# Run with verbose output
pytest -v
```

## Development

### Setting Up Development Environment

```bash
git clone https://github.com/yourusername/raftengine.git
cd raftengine

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in development mode
pip install -e ".[dev]"

# Run tests
pytest
```

### Code Quality

The project uses several tools for code quality:

```bash
# Code formatting
black raftengine/

# Type checking
mypy raftengine/

# Linting
flake8 raftengine/
```

### Multi-Version Testing

Test against multiple Python versions using tox:

```bash
tox
```

## Examples

The `demos/` directory contains complete examples:

- **Banking System**: A distributed banking application showing how to integrate RaftEngine
- **Auction System**: A distributed auction platform with real-time bidding
- **Key-Value Store**: A simple distributed key-value store implementation

## Documentation

- [API Reference](https://raftengine.readthedocs.io/en/latest/api/)
- [User Guide](https://raftengine.readthedocs.io/en/latest/guide/)
- [Developer Documentation](https://raftengine.readthedocs.io/en/latest/developer/)

## Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

### Development Workflow

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Run the test suite
6. Submit a pull request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE.md) file for details.

## Acknowledgments

- The Raft algorithm was developed by Diego Ongaro and John Ousterhout
- [Original Raft Paper](https://raft.github.io/raft.pdf)
- [Raft Consensus Algorithm](https://raft.github.io/)

## Support

- [GitHub Issues](https://github.com/yourusername/raftengine/issues)
- [Discussions](https://github.com/yourusername/raftengine/discussions)
- [Documentation](https://raftengine.readthedocs.io/)

---

**Note**: This library is in active development. The API may change in future versions. Please pin to specific versions in production environments.