# PRD: Prototype 1 - Record Stream Files Implementation

## Overview

Prototype 1 implements a simplified version of the Record Stream Files concept from the LSFS experiment project. This prototype focuses on demonstrating core functionality for writing and reading record-oriented data with block-based storage.

## Goals

1. Validate the basic Record Stream Files architecture
2. Implement core block-based writing and reading mechanisms
3. Create foundation for future log-structured file system features
4. Test record slicing and reconstruction logic

## Scope

### In Scope
- Basic Record Stream Files implementation
- Block-based storage with 4096-byte blocks
- Record slicing across blocks
- Simple catalog-based reading
- JSON serialization for test data
- Comprehensive pytest test suite with coverage reporting
- Raft log example implementation demonstrating LogAPI interface

### Out of Scope
- Direct IO operations (ordinary file IO only)
- Complex error handling
- Performance optimization
- Data compression
- CRC validation

## Requirements

### Test Data Generation
- Generate test dictionary with 5 key-value pairs
- Keys: random lowercase letters
- Values: random integers
- Serialize using `json.dumps()` and encode to bytes

### BlockWriter Class

**Core Properties:**
- `block_buffer`: 4096-byte buffer
- Record index: monotonically incrementing integer
- First/last record index tracking
- `min_content_size`: minimum content size threshold

**Methods:**

1. **Record Processing:**
   - Accept Record Structure Header, Trailer, and bytes object
   - Create "sausage" object combining header, data, and trailer
   - Calculate total content size

2. **Slice Management:**
   - Calculate trial sausage size (content + slice header/trailer)
   - Test remaining block buffer space
   - If fits: write complete slice to buffer
   - If not: slice sausage to fit remaining space

3. **Buffer Management:**
   - Check remaining space after write
   - Compare against minimum space requirements:
     - Slice header/trailer pair
     - Record header/trailer pair  
     - `min_content_size` bytes
   - If insufficient space: pad to 4096 bytes and write to file

4. **File Operations:**
   - `flush()`: pad and write any remaining buffer content
   - `close()`: call flush() and close file
   - Return record index to caller

### Recorder Class

**Functionality:**
- Accept bytes object and integer `record_type_code`
- Create Record Structure Header
- Maintain in-memory cache of last X records (configurable `cache_size`)
- Submit to BlockWriter and receive record index

### BlockReader Class

**Catalog Building:**
- Record index
- Record type_code
- First slice location (block number + offset)
- Last slice location (block number + offset)
- Track first and last record index values

**Methods:**
- `get_record(index)`: return original bytes and record type code

## Technical Specifications

### Block Structure
- Size: 4096 bytes
- Header: `magic number | byte count`
- Trailer: `magic number | byte count | last slice start`

### Record Structure
- Header: `magic number | record index | user type code (64 bits)`
- Trailer: `magic number | record index | user type code (64 bits) | first block number | first block offset`

### Slice Structure
- Header: `magic number | record index | slice number`
- Trailer: `magic number | record index | slice number | block offset of start`

## Testing Requirements

### Pytest Test Suite
- Convert initial test script to pytest format with proper fixtures
- Add `@pytest.mark.asyncio` decorators for async test support
- Configure pytest.ini with coverage reporting and asyncio mode
- Create coverage.cfg for detailed coverage analysis
- Include tests for:
  - Single record write/read operations
  - Multiple record operations
  - Recorder cache functionality
  - Error handling (nonexistent records, empty data)
  - Edge cases and boundary conditions

### Test Infrastructure
- requirements.txt with pytest, pytest-cov, pytest-asyncio
- Virtual environment setup (.venv)
- HTML coverage reporting
- Temporary file fixtures for clean test isolation

## Example Implementation Requirements

### Raft Log Example
- Create examples/raft_log directory structure
- Implement LSFSRaftLog class conforming to LogAPI interface
- Support full Raft consensus algorithm requirements:
  - Term management and persistence
  - Vote tracking
  - Log entry append/read operations
  - Cluster configuration management
  - Snapshot support
- Demonstrate real-world usage patterns
- Include comprehensive demo functionality

### LogAPI Interface Compliance
- Implement all abstract methods from log_api.py
- Support LogRec dataclass with all required fields
- Handle RecordCode enum types properly
- Provide cluster configuration serialization/deserialization
- Support snapshot installation and retrieval

## Success Criteria

1. Successfully write test dictionary data to block-structured file
2. Read and reconstruct original data with correct type codes
3. Handle records that span multiple blocks (slicing)
4. Maintain accurate record catalog for efficient retrieval
5. Demonstrate round-trip data integrity (write → read → verify)
6. **Achieve comprehensive test coverage with pytest suite**
7. **Pass all async tests with proper pytest-asyncio integration**
8. **Demonstrate full LogAPI interface implementation with Raft example**
9. **Show persistence and recovery of Raft state across sessions**

## Implementation Notes

- Use ordinary file IO (not direct IO for this prototype)
- Follow exploratory code guidelines (minimal error checking, print statements)
- Use async methods by default
- Classes preferred over functions for domain separation
- **Separate log records and metadata into different LSFS files**
- **Maintain in-memory caching for performance while ensuring persistence**
- **Handle import conflicts (renamed types.py to raft_types.py)**