# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Multi-version testing support with tox
- Enhanced documentation and examples

### Changed
- TBD

### Fixed
- TBD

## [0.1.0] - 2024-01-XX

### Added
- Initial release of RaftEngine
- Core Raft consensus algorithm implementation
- DeckAPI - Main entry point and control interface
- PilotAPI - User-supplied interface for transport and storage
- LogAPI - Interface for persistent log storage
- SnapShotAPI - Interface for snapshot management
- Event system for monitoring and debugging
- Comprehensive role implementations (Leader, Follower, Candidate)
- Message types for all Raft protocol operations:
  - RequestVote and RequestVoteResponse
  - AppendEntries and AppendResponse
  - PreVote and PreVoteResponse (for election optimization)
  - TransferPower and TransferPowerResponse
  - MembershipChange and MembershipChangeResponse
  - SnapShot and SnapShotResponse
- Configuration classes (LocalConfig, ClusterInitConfig)
- Type definitions and enums (RoleName, OpDetail, RecordCode)
- Extensive test suite with detailed execution tracing
- Development tools for debugging and visualization
- Demo applications (banking system, auction platform)
- Documentation and API reference

### Features
- **Pure Python**: No external dependencies beyond Python standard library
- **Async-First**: Built on asyncio for high-performance concurrent operations
- **Modular Design**: Clean separation between Raft logic and transport/storage
- **Pluggable Storage**: Support for any database or storage system
- **Flexible Transport**: Support for HTTP, gRPC, message queues, WebSockets, etc.
- **Event-Driven**: Comprehensive event system for monitoring and debugging
- **Test Coverage**: Extensive test suite with scenario-based testing
- **Development Tools**: Advanced tracing and visualization capabilities

### Supported Python Versions
- Python 3.8+
- Python 3.9+
- Python 3.10+
- Python 3.11+
- Python 3.12+

### Known Limitations
- This is an alpha release intended for evaluation and development
- API may change in future versions
- Performance optimizations are ongoing
- Documentation is still being expanded

### Migration from Pre-Release
- N/A (initial release)

### Dependencies
- Python 3.8+ (uses dataclasses, typing, asyncio)
- No external runtime dependencies
- Development dependencies: pytest, coverage, black, mypy, flake8

[Unreleased]: https://github.com/yourusername/raftengine/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/yourusername/raftengine/releases/tag/v0.1.0