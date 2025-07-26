# LSFS Experiment Project

## Project Overview

This project implements a log-structured file system mechanism in Python for storage and retrieval of record-oriented user data. The design prioritizes maximum write performance, potentially at the cost of read performance and complexity.

### Core Features

1. **Direct IO Operations**: Primary writes use direct IO features with fallback to ordinary file IO
2. **Three Record Types**:
   - **Record Streams**: Event logs
   - **Data Streams**: Arbitrary data portions (e.g., file chunks during download)
   - **Final Data**: Complete state declarations independent of previous records

### Architecture Notes

- Out-of-process clerk process for index assembly to optimize read performance
- No CRCs used (relying on modern filesystem error detection/correction)
- Optimized for Raft consensus algorithm use cases

## File Structure Specifications

### Record Stream Files

**Components:**
- **Block**: Fixed-size container for direct IO
- **Record**: User data wrapper with header/tailer
- **Slice**: Record portion wrapper for block fitting

**Block Structure:**
- Header: `magic number | byte count`
- Tailer: `magic number | byte count | last slice start`

**Record Structure:**
- Header: `magic number | record index | user type code (64 bits)`
- Tailer: `magic number | record index | user type code (64 bits) | first block number | first block offset`

**Slice Structure:**
- Header: `magic number | record index | slice number`
- Tailer: `magic number | record index | slice number | block offset of start`

### Data Stream Files

**Components:**
- **Block**: Same as Record Streams
- **Mark**: Stream end marker

Always paired with Final Data file containing last Mark location.

**Mark Structure:**
`magic number | byte count | first block number | first block offset | last block number`

### Final Data Files

Implemented as paired Record Stream files ("A" and "B") with alternating write pattern based on configured block limits.

## Development Guidelines

### Code Style (Exploratory Phase)
- Use `print()` instead of logging
- Minimal error checking - let code fail fast
- No exception handling except where absolutely necessary (use `traceback.print_exc()`)
- Python builtins only unless specifically directed
- No docstrings (rapid iteration focus)
- Classes/methods preferred over functions for clear domain separation
- Default to async methods for event loop consideration

### Experiment Protocol

When starting experiments (declared with "Start an experiment..."):
1. Save experiment info in `experiments.md` with unique number
2. Method changes: Create new methods (e.g., `do_foo` → `do_foo_exp_1`)
3. Class changes: Create child classes or new classes (e.g., `Foo` → `Foo_exp_1`)
4. Usage changes: Wrap in experiment flags for easy switching
5. Mark all experimental changes for easy identification
6. Terminate with "adopt experiment N" or "discard experiment N"

### Task Management

- Use TodoWrite tool for planning complex tasks
- Mark todos as completed immediately after finishing
- Only have one task in_progress at a time
- Run lint/typecheck commands when available before considering tasks complete