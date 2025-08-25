# Product Requirements Document (PRD)
## Test Conversion: ClusterMgr to Command Line Interface

### Project Overview

**Project Name**: Cluster Command Test Conversion
**Version**: 1.0
**Date**: August 25, 2025

### Background

The `tests/test_cluster_cmd.py` file currently contains a hybrid test approach where some operations use command line interface testing (via the `run_command` function) while the majority still use direct `ClusterMgr` method calls. This inconsistency needs to be resolved to properly test the command line interface functionality of `cluster_cmd.py`.

### Problem Statement

The current test file `tests/test_cluster_cmd.py` has:
- **2 operations converted** to command line approach (lines 81 and 93)
- **~40+ operations remaining** that use direct `ClusterMgr` method calls
- Mixed testing approaches that don't fully validate the command line interface
- Incomplete coverage of the `main()` function in `src/ops/cluster_cmd.py`

### Goals & Success Criteria

**Primary Goal**: Convert all remaining `ClusterMgr` method calls in `tests/test_cluster_cmd.py` to use command line interface testing via the `run_command` function.

**Success Criteria**:
1. **100% Conversion**: All `ClusterMgr` method invocations replaced with `run_command` calls
2. **Test Functionality Preserved**: All existing test logic and assertions maintained
3. **JSON Output Handling**: Proper conversion from object property access to dictionary access
4. **Test Execution Success**: All tests pass after conversion
5. **No Source Code Changes**: Zero modifications to `src/` tree files

### Functional Requirements

#### FR1: ClusterMgr Method Replacement
- Replace all direct calls to `ClusterMgr` methods with equivalent `run_command` calls
- Use `find_local=True` for cluster discovery operations
- Use `--json` flag for all command line operations
- Handle JSON output parsing with `json.loads()`

#### FR2: Object Access Pattern Conversion
- Convert object property access patterns (e.g., `server.uri`, `config.uri`) to dictionary access (e.g., `server['uri']`, `config['uri']`)
- Maintain equivalent data validation and assertions
- Preserve all existing test logic flow

#### FR3: Error Handling Preservation
- Maintain all existing exception handling and `pytest.raises()` assertions
- Ensure command line operations produce equivalent error conditions
- Preserve timeout and retry logic where applicable

#### FR4: Data Format Consistency
- Ensure JSON output from command line matches expected data structures
- Handle conversion of `ClusterServerConfig` objects to/from dictionary representation
- Maintain compatibility with existing validation logic

### Technical Requirements

#### TR1: Test File Modifications
- **File**: `tests/test_cluster_cmd.py` only
- **Scope**: Function `test_run_ops_full()` only
- **Pattern**: Use existing `run_command()` function for all operations

#### TR2: Command Line Interface Usage
- **Discovery**: Always use `find_local=True` for cluster location
- **Output**: Always use `json_output=True` (--json flag)
- **Operations**: Map each `ClusterMgr` method to appropriate `--run-ops` value

#### TR3: Data Handling
- **Input**: Parse JSON strings with `json.loads()`
- **Validation**: Convert object assertions to dictionary key access
- **Types**: Handle `ClusterServerConfig.from_dict()` conversions where needed

### Operation Mapping

| ClusterMgr Method | Command Line Operation | Notes |
|------------------|----------------------|--------|
| `find_clusters()` | `list_clusters` | Directory-based discovery |
| `list_clusters()` | `list_clusters` | Cluster enumeration |
| `cluster_status()` | `cluster_status` | Status information |
| `start_servers()` | `start_servers` | Server startup |
| `stop_cluster()` | `stop_cluster` | Cluster shutdown |
| `stop_server()` | `stop_server` | Individual server stop |
| `server_status()` | `server_status` | Server status check |
| `log_stats()` | `log_stats` | Log statistics |
| `send_heartbeats()` | `send_heartbeats` | Heartbeat operations |
| `take_snapshot()` | `take_snapshot` | Snapshot creation |
| `server_exit_cluster()` | `server_exit_cluster` | Server removal |

### Non-Requirements

#### What Will NOT Be Done
- **Source Code Modification**: No changes to `src/` tree files
- **Test Logic Changes**: No modifications to test flow or assertions
- **New Test Features**: No additional test coverage beyond existing scope
- **Mock Framework Usage**: No additional mock features beyond existing `run_command` implementation
- **Performance Optimization**: No focus on test execution speed improvements

### Risk Assessment

#### Low Risk
- **Pattern Consistency**: Existing `run_command` function provides proven conversion pattern
- **JSON Format**: Well-documented output format with comprehensive examples
- **Scope Limitation**: Changes confined to single test file

#### Medium Risk
- **Complex Object Conversions**: Some operations return nested objects requiring careful dictionary conversion
- **Error Condition Mapping**: Ensuring command line operations produce equivalent exceptions
- **Timing Dependencies**: Some operations have timing requirements that may need adjustment

#### Mitigation Strategies
- **Incremental Approach**: Convert operations one at a time with immediate testing
- **JSON Validation**: Use provided JSON examples to verify correct data handling
- **Error Testing**: Explicitly test that command line operations fail appropriately

### Acceptance Criteria

#### Test Execution
- [ ] All tests in `tests/test_cluster_cmd.py` pass
- [ ] No `ClusterMgr` method calls remain in the test (except initialization of `setup_mgr` if needed for cleanup)
- [ ] All assertions and validations continue to work correctly

#### Code Quality
- [ ] No modifications to `src/` tree files
- [ ] Consistent use of `run_command` function pattern
- [ ] Proper JSON parsing and dictionary access throughout
- [ ] Preserved error handling and exception testing

#### Documentation
- [ ] Clear commit messages documenting each conversion step
- [ ] Implementation plan and checklist completed and maintained

### Dependencies

- **Existing Code**: `run_command()` function in `tests/test_cluster_cmd.py`
- **Command Interface**: `cluster_cmd.py` main function with JSON output support
- **Test Framework**: pytest and existing test infrastructure

### Timeline

**Phase 1**: PRD Approval → Implementation Plan Creation (1-2 iterations)
**Phase 2**: Systematic conversion following checklist (Multiple iterations)
**Phase 3**: Final validation and approval (1 iteration)

### Approval Required

This PRD requires approval before proceeding to implementation plan creation.