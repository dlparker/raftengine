# Raft Feature Identification and Analysis Methodology

## Overview

This document provides a systematic methodology for identifying and documenting Raft consensus algorithm elements in test traces, with specific focus on mapping test behaviors to Diego Ongaro's Raft thesis concepts.

## Background: Existing Infrastructure

### Test Tracing System
The raftengine project has a sophisticated tracing infrastructure:

- **Trace Generation**: Every test captures detailed execution traces in multiple formats
- **Output Formats**: JSON (raw data), CSV (tabular), RST (documentation), PlantUML (sequence diagrams)
- **Storage**: `captures/test_traces/` with subdirectories by format
- **Control**: `dev_tools/trace_output.py`, `dev_tools/build_docs.py`

### Feature Registry System
- **Location**: `dev_tools/features.py`, `dev_tools/feature_db.py`
- **Structure**: Hierarchical naming with dot notation (e.g., `state_machine_command.request_redirect`)
- **Database**: SQLite storage in `captures/features/features.db`
- **Documentation**: Auto-generated RST fragments in `captures/features/docs/`

### Existing Documentation Structure
- **Manual Docs**: `docs/source/developer/tests/features/`
- **Auto-Generated**: Test-specific RST files with collapsible trace tables
- **Cross-References**: Links between tests and feature documentation

## Methodology for Raft Element Identification

### 1. Message Flow Analysis

**Approach**: Parse JSON trace files to extract Raft protocol messages and map to thesis sections.

**Key Message Types and Thesis Mappings**:

```
Message Code         | Thesis Section | Description
---------------------|----------------|----------------------------------
pre_vote            | 4.2.1          | Pre-Vote extension for stability
request_vote        | 3.4            | Leader Election core protocol  
vote_response       | 3.4            | Election vote responses
append_entries      | 3.5            | Log Replication protocol
append_response     | 3.5            | Log replication responses
transfer_power      | 6.4            | Leadership Transfer extension
membership_change   | 4.1            | Cluster Configuration Changes
snapshot            | 5              | Log Compaction via snapshots
```

**Implementation Pattern**:
```python
def analyze_message_flow(trace_data):
    """Extract and categorize Raft messages from trace"""
    for trace_line in trace_data['trace_lines']:
        for node_state in trace_line:
            if node_state.get('message_action') == 'sent':
                message = node_state['message']
                message_code = message['code']
                # Map to thesis section using lookup table
                thesis_section = MESSAGE_TO_THESIS_MAP[message_code]
                # Extract protocol parameters for validation
                extract_protocol_parameters(message, message_code)
```

### 2. State Transition Analysis

**Approach**: Track node role changes and validate against Raft state machine rules.

**Role Transitions and Validation**:
- `FOLLOWER → CANDIDATE`: Must increment term, start election timer
- `CANDIDATE → LEADER`: Must receive majority votes for current term
- `LEADER → FOLLOWER`: Must discover higher term or lose connectivity
- `CANDIDATE → FOLLOWER`: Must receive higher term or election timeout

**Log State Tracking**:
- **Index Progression**: Must be monotonically increasing per node
- **Term Consistency**: Log entries at same index must have consistent terms
- **Commit Index**: Must never decrease, only advance with majority agreement

### 3. Safety Property Verification

**The Five Raft Safety Properties** (Thesis Section 3.2):

1. **Election Safety**: At most one leader per term
2. **Leader Append-Only**: Leader never overwrites/deletes log entries  
3. **Log Matching**: Identical logs up to any given index across nodes
4. **Leader Completeness**: Leader contains all committed entries from previous terms
5. **State Machine Safety**: Applied commands produce identical results

**Verification Implementation**:
```python
def verify_safety_properties(trace_data):
    """Validate Raft safety properties hold throughout execution"""
    leaders_per_term = {}
    node_logs = {}
    commit_indices = {}
    
    for trace_line in trace_data['trace_lines']:
        term = extract_current_term(trace_line)
        
        # Election Safety check
        current_leaders = [node for node in trace_line 
                          if node['role_name'] == 'LEADER']
        if len(current_leaders) > 1 and same_partition(current_leaders):
            raise SafetyViolation("Multiple leaders in same partition")
            
        # Log Matching check  
        validate_log_consistency(node_logs)
        
        # Leader Completeness check
        validate_leader_has_committed_entries(trace_line)
```

### 4. Feature Classification Framework

**Primary Feature Categories** (Based on Thesis Structure):

#### Leader Election (`leader_election`)
- **Base**: Normal election process (3.4)
- **Branches**:
  - `normal_election`: Happy path, all nodes vote yes
  - `split_vote`: No majority achieved, retry needed
  - `with_pre_vote`: Using Pre-Vote extension (4.2.1)
  - `without_pre_vote`: Basic algorithm only
  - `higher_term_discovery`: Candidate discovers higher term
  - `log_inconsistency_rejection`: Vote rejected due to log staleness

#### Log Replication (`log_replication`)
- **Base**: AppendEntries protocol (3.5)
- **Branches**:
  - `normal_replication`: In-sync followers accept immediately
  - `slow_follower_backdown`: Leader backtracks to find match point
  - `conflict_resolution`: Overwriting inconsistent entries
  - `heartbeat_only`: Empty AppendEntries for leader confirmation

#### State Machine Commands (`state_machine_command`)
- **Base**: Client command processing (6)
- **Branches**:
  - `all_in_sync`: Normal command execution path
  - `request_redirect`: Non-leader redirects to current leader
  - `retry_during_election`: Temporary unavailability response
  - `apply_on_delayed_replication`: Command applied after catch-up
  - `minimal_node_count`: Command succeeds with minimum quorum

#### Network Partitions (`network_partition`)
- **Base**: Split-brain prevention and recovery
- **Branches**:
  - `majority_partition_continues`: Majority side remains active
  - `minority_partition_blocks`: Minority cannot make progress
  - `partition_recovery`: Network heal and state reconciliation

#### Membership Changes (`membership_changes`)
- **Base**: Cluster reconfiguration (4.1)
- **Branches**:
  - `add_follower`: Adding new node to cluster
  - `remove_follower`: Removing existing follower
  - `remove_leader`: Removing current leader node

### 5. Test Analysis Template

For any test, follow this analysis pattern:

#### Step 1: Extract Test Metadata
```python
def analyze_test(test_json_path):
    """Standard test analysis workflow"""
    with open(test_json_path) as f:
        trace_data = json.load(f)
    
    test_info = {
        'name': trace_data['test_name'],
        'path': trace_data['test_path'], 
        'description': trace_data['test_doc_string'],
        'sections': extract_test_sections(trace_data)
    }
```

#### Step 2: Identify Used vs Tested Features
- **Used Features**: Operations performed to set up test conditions
- **Tested Features**: Behaviors being explicitly validated

#### Step 3: Map to Thesis Concepts
- Extract message sequences and validate against expected patterns
- Identify which thesis sections are exercised
- Note any deviations or extensions beyond basic algorithm

#### Step 4: Generate Feature Mappings
```python
def generate_feature_mappings(test_analysis):
    """Create feature registry entries for test"""
    for section in test_analysis['sections']:
        for feature_path in section['used_features']:
            registry.mark_feature_usage(test_name, section_idx, feature_path, 'uses')
        for feature_path in section['tested_features']:
            registry.mark_feature_usage(test_name, section_idx, feature_path, 'tests')
```

## Example: test_command_2_leaders_3 Analysis

### Test Overview
- **Purpose**: Validate command redirect after leader partition
- **Scenario**: Leader gets partitioned, new election occurs, old leader rejoins and receives command request
- **Expected Behavior**: Command request redirected to current leader

### Section-by-Section Analysis

#### Section 1: Normal Election
- **Used Features**: `leader_election.all_yes_votes.with_pre_vote`
- **Thesis Mapping**: Sections 3.4 (election) + 4.2.1 (pre-vote)
- **Key Validation**: Single leader elected, TERM_START record replicated

#### Section 2: Running Command Normally  
- **Used Features**: `state_machine_command.all_in_sync`
- **Thesis Mapping**: Section 6 (client interaction)
- **Key Validation**: Command succeeds at leader, replicates to followers

#### Section 3: Simulating Network Problems
- **Tested Features**: `network_partition.leader_isolation`
- **Thesis Mapping**: Safety properties maintenance during partition
- **Key Validation**: Partitioned leader cannot commit commands

#### Section 4: New Election
- **Used Features**: `leader_election.authorized_campaign`
- **Thesis Mapping**: Section 3.4 with higher term
- **Key Validation**: New leader elected with higher term

#### Section 5: Command Redirect Test
- **Tested Features**: `state_machine_command.request_redirect`
- **Thesis Mapping**: Section 6 (non-leader command handling)
- **Key Validation**: Old leader redirects command to new leader

### Missing Feature Definitions Required
Based on this analysis, these feature branches need to be created:
- `leader_election.post_partition_recovery`
- `state_machine_command.leader_discovery_redirect`  
- `network_partition.split_brain_prevention`

## Implementation Guidelines

### For Analyzing New Tests

1. **Load test metadata**: `captures/test_traces/metadata/{test_path}/{test_name}.json` (5KB vs 485KB for full JSON)
2. **Load digest CSV trace**: `captures/test_traces/digest_csv/{test_path}/{test_name}.csv` (includes original_line_index column)
3. **Extract test structure**: Use `test_doc_string` and section markers from metadata
4. **Analyze message flows**: Parse CSV for message events, use original_line_index to correlate with sections
5. **Identify state transitions**: Track role changes and log evolution from CSV data
6. **Validate safety properties**: Ensure Raft invariants hold using filtered trace data
7. **Generate feature mappings**: Create appropriate registry entries
8. **Update test with feature registry**: Modify test file to use registry.get_raft_feature()
9. **Create feature and feature branch definition files**: Create the feature definition files in `docs/source/tests/features/` instead of the `captures/` tree. Follow the directory layout pattern used by the generated test rst files. Update existing files if they need improvement.
10. **Generate documentation**: Run trace generation and documentation build (`dev_tools/build_docs.py`)
11. **Copy generated test rst files**: Once the target test is updated with feature definition files, tests pass, and doc build script has been run, copy the new test rst files from captures to docs according to the mapping table below
12. **Update features_in_tests.rst**: Create or update `docs/source/developer/tests/features_in_tests.rst` with comprehensive feature-to-test mapping tables (see below)
13. **Update test feature definitions checklist**: Mark the test as complete (✓) in `claude_plans/test_feature_definitions_checklist.md` and update the completion statistics
14. **VALIDATION CHECKLIST**: Perform critical format checks (see below)
15. **Report created files**: List all new feature documentation files for manual integration

### Test RST File Copy Mapping

Copy `captures/test_traces/rst/(COLUMN 2)` to `COLUMN 3`:

| Test file name         | Capture RST               | Doc dir                                     |
|------------------------|---------------------------|---------------------------------------------|
| test_elections_1.py    | test_elections_1/*.rst    | docs/source/developer/tests/elections      |
| test_elections_2.py    | test_elections_2/*.rst    | docs/source/developer/tests/elections      |
| test_commands_1.py     | test_commands_1/*.rst     | docs/source/developer/tests/commands       |
| test_partitions_1.py   | test_partitions_1/*.rst   | docs/source/developer/tests/partitions     |
| test_snapshots.py      | test_snapshots/*.rst      | docs/source/developer/tests/snapshots      |
| test_member_changes.py | test_member_changes/*.rst | docs/source/developer/tests/member_changes |
| test_log_fiddles.py    | test_log_fiddles/*.rst    | docs/source/developer/tests/log_recovery   |
| test_class_edges.py    | test_class_edges/*.rst    | docs/source/developer/tests/edges          |
| test_msg_edges.py      | test_msg_edges/*.rst      | docs/source/developer/tests/edges          |
| test_events.py         | test_events/*.rst         | docs/source/developer/tests/events         |
| test_timers_1.py       | test_timers_1/*.rst       | docs/source/developer/tests/timers         |
| test_random_code.py    | test_random_code/*.rst    | docs/source/developer/tests/random_code    |

### PlantUML Diagram Copy Mapping

Copy `captures/test_traces/plantuml/TEST_PATH*/test_name*.puml` to `docs/source/developer/tests/diagrams/TEST_PATH*` where TEST_PATH* is something like test_elections_1 or test_elections_2.

### Build Documentation Script Enhancement

Enhanced `dev_tools/build_docs.py` with optional copy operations:

```bash
# Generate documentation only (default behavior)
python dev_tools/build_docs.py

# Generate documentation AND copy files to docs tree
python dev_tools/build_docs.py --copy-to-docs

# With verbose output showing each copied file
python dev_tools/build_docs.py --copy-to-docs --verbose
```

The `--copy-to-docs` flag copies generated RST and PlantUML files from `captures/test_traces/` to the appropriate directories in `docs/source/developer/tests/` according to the mapping table above. This allows users to choose whether to copy the generated test files during the build process.

### Features in Tests Documentation

Create or update `docs/source/developer/tests/features_in_tests.rst` with comprehensive feature-to-test mapping tables. This file should contain:

#### Structure of features_in_tests.rst

```rst
Features in Tests
=================

This document provides a comprehensive mapping between Raft features and the tests that exercise them.

Features That Are Tested
-------------------------

The following table shows features that are explicitly tested (validated) by test cases:

.. list-table:: Features Under Test
   :header-rows: 1
   :widths: 50 50

   * - Feature
     - Tests That Test This Feature
   * - Leader Election: Normal Election
     - test_elections_1::test_election_1, test_elections_1::test_election_2
   * - Leader Election: Split Vote Recovery
     - test_elections_2::test_failed_first_election_1, test_elections_2::test_failed_first_election_2
   * - State Machine Command: Request Redirect
     - test_commands_1::test_command_2_leaders_3
   * - Network Partition: Leader Isolation
     - test_partition_1::test_partition_2_leader, test_partition_1::test_partition_3_leader

Features That Are Used (But Not Tested)
----------------------------------------

The following table shows features that are used by tests to set up conditions but are not the primary focus of testing:

.. list-table:: Features Used by Tests
   :header-rows: 1
   :widths: 50 50

   * - Feature  
     - Tests That Use This Feature
   * - Leader Election: All Yes Votes with Pre-Vote
     - test_commands_1::test_command_1, test_commands_1::test_command_2_leaders_1, test_snapshots::test_snapshot_1
   * - State Machine Command: All In Sync
     - test_commands_1::test_command_2_leaders_3, test_partition_1::test_partition_1
   * - Log Replication: Normal Replication
     - test_commands_1::test_command_1, test_commands_1::test_full_catchup
```

#### Content Generation Guidelines

1. **Feature Descriptions**: Use the short description from the feature definition files (short.rst)
2. **Test References**: Use the format `test_file::test_method` for precise identification
3. **Categorization**: Clearly distinguish between features that are tested vs. used
4. **Alphabetical Ordering**: Sort features alphabetically within each category
5. **Cross-References**: Include links to feature definition files where appropriate

#### Automation Integration

The features_in_tests.rst file should be automatically generated or updated by parsing:
- The feature registry database (`captures/features/features.db`)
- Test feature usage annotations in test files
- Feature definition files in `docs/source/tests/features/`

This ensures the mapping tables stay synchronized with the actual test suite and feature definitions.

## Optimized File Structure for Analysis

### Problem Solved
Large JSON trace files (485KB+) caused analysis tools to hit size limits. The solution splits trace data into optimized formats:

### New File Structure

**Metadata Files** (`captures/test_traces/metadata/`):
- Contains test structure, sections, and feature mappings
- **Size**: ~5KB (97% reduction from full JSON)
- **Usage**: Load for test structure and section boundaries

**Enhanced Digest CSV** (`captures/test_traces/digest_csv/`):
- Contains filtered trace events (sent/handled_in messages only)
- **New column**: `original_line_index` - maps to original trace line positions
- **Size**: ~23KB (95% reduction from full JSON)
- **Usage**: Primary data source for message flow analysis

**Full JSON** (`captures/test_traces/json/`):
- Complete trace data (preserved for debugging)
- **Size**: ~485KB
- **Usage**: Debugging only, not recommended for analysis

### Analysis Workflow Using New Format

```python
# Load test metadata (fast, small file)
with open('captures/test_traces/metadata/test_commands_1/test_command_1.json') as f:
    metadata = json.load(f)

# Get test structure
test_sections = metadata['test_sections']
test_name = metadata['test_name']

# Load digest CSV for trace analysis
import pandas as pd
df = pd.read_csv('captures/test_traces/digest_csv/test_commands_1/test_command_1.csv')

# Correlate CSV rows with test sections using original_line_index
for section_id, section in test_sections.items():
    start_pos = section['start_pos']
    end_pos = section['end_pos']
    
    # Find CSV rows that fall within this section
    section_events = df[
        (df['original_line_index'] >= start_pos) & 
        (df['original_line_index'] <= end_pos)
    ]
    
    # Analyze message flows for this section
    messages = section_events[section_events['event'] == 'MESSAGE_OP']
    # ... perform analysis
```

### Benefits
- **97% file size reduction** for analysis tools
- **Faster loading and parsing** using CSV format
- **Maintains all analysis capabilities** through original_line_index mapping
- **Preserves full JSON for debugging** when needed
- **Leverages existing filtering logic** from digest CSV generation

### For Adding New Feature Definitions

1. **Follow naming convention**: `{primary_feature}.{scenario_branch}`
2. **Create documentation stubs**: Use `dev_tools/build_docs.py` auto-generation
3. **Add thesis references**: Include section numbers in narrative documentation
4. **Define test criteria**: Specify what constitutes using vs testing the feature
5. **CRITICAL: Validate RST formatting**: 
   - Remove `:orphan:` directives from all generated RST files
   - Remove section titles/headings from narrative files (they are included content)
6. **Report new feature files**: List all created feature documentation files for manual placement

## CRITICAL VALIDATION CHECKLIST

After generating feature documentation, these checks MUST be performed before integration:

### RST Format Validation

1. **Remove `:orphan:` directives**:
   ```bash
   find captures/features/docs -name "*.rst" -exec grep -l ":orphan:" {} \;
   # If any files found, remove the orphan lines:
   find captures/features/docs -name "*.rst" -exec sed -i '/^:orphan:$/d' {} \;
   ```

2. **Remove section titles from narrative files**:
   ```bash
   # Check for files with leading titles (lines 1-3 typically contain title + underline)
   find captures/features/docs -name "narative.rst" -exec head -3 {} \;
   # Remove title and underline from narrative files (they are included content):
   find captures/features/docs -name "narative.rst" -exec sed -i '1,2d' {} \;
   ```

3. **Remove leading blank lines**:
   ```bash
   # Check for files starting with blank lines
   find captures/features/docs -name "*.rst" -exec awk 'FNR==1 && /^$/ {print FILENAME}' {} \;
   # Remove leading blank lines:
   find captures/features/docs -name "*.rst" -exec sed -i '1{/^$/d}' {} \;
   ```

### Documentation Build Test

4. **Test Sphinx build**:
   ```bash
   cd docs && make clean && make html 2>&1 | grep -i "critical\|error"
   # Should produce no CRITICAL errors about "Unexpected section title"
   ```

5. **Install missing Sphinx extensions** (if needed):
   ```bash
   pip install sphinx-collapse  # For .. collapse:: directive support
   ```

### Feature File Integration Report

6. **Generate file list for manual integration**:
   ```bash
   echo "=== NEW FEATURE FILES CREATED ==="
   find captures/features/docs -name "*.rst" -newer <reference_file> | sort
   echo "=== FILES TO COPY TO docs/source/developer/tests/features/ ==="
   ```

   **Manual Integration Steps**:
   - Copy the listed files to `docs/source/developer/tests/features/` maintaining directory structure
   - Ensure the same RST formatting fixes are applied to the copied files
   - Verify the feature files are properly excluded by `exclude_patterns` in `conf.py`

## FINAL STEP: New Feature Files Report

After completing the analysis and documentation generation, provide a summary report:

### Example Report Format:
```
=== RAFT FEATURE ANALYSIS COMPLETE ===

Test Analyzed: test_commands_1::test_command_2_leaders_3

NEW FEATURE FILES CREATED:
- captures/features/docs/leader_election/branches/partition_recovery/narative.rst
- captures/features/docs/leader_election/branches/partition_recovery/features.rst  
- captures/features/docs/leader_election/branches/partition_recovery/short.rst
- captures/features/docs/state_machine_command/branches/discovery_redirect/narative.rst
- captures/features/docs/state_machine_command/branches/discovery_redirect/features.rst
- captures/features/docs/state_machine_command/branches/discovery_redirect/short.rst
- captures/features/docs/network_partition/branches/leader_isolation/narative.rst
- captures/features/docs/network_partition/branches/leader_isolation/features.rst
- captures/features/docs/network_partition/branches/leader_isolation/short.rst

VALIDATION STATUS:
✓ All :orphan: directives removed
✓ All section titles removed from narrative files  
✓ All leading blank lines removed
✓ Sphinx build successful (no CRITICAL errors)
✓ sphinx-collapse extension installed

INTEGRATION READY: Files are ready for manual copying to docs/source/developer/tests/features/
```

This report makes it easy to identify exactly which files were created and need to be integrated into the documentation tree.

### Tools and Automation

#### Recommended Analysis Tools
```bash
# Extract test traces for analysis
python dev_tools/build_docs.py

# Run specific test with tracing
./run_tests.sh tests/test_commands_1.py::test_command_2_leaders_3

# Generate documentation 
python dev_tools/build_docs.py
```

#### Analysis Script Template
```python
#!/usr/bin/env python
"""Template for automated Raft feature analysis"""

def analyze_raft_test(test_path, test_name):
    # Load trace data
    trace_file = f"captures/test_traces/json/{test_path}/{test_name}.json"
    
    # Extract message patterns
    messages = extract_message_sequences(trace_file)
    
    # Map to thesis concepts
    thesis_mappings = map_to_thesis_sections(messages)
    
    # Validate safety properties
    safety_validation = verify_safety_properties(trace_file)
    
    # Generate feature mappings
    feature_mappings = generate_feature_mappings(thesis_mappings)
    
    return {
        'thesis_mappings': thesis_mappings,
        'safety_validation': safety_validation,
        'feature_mappings': feature_mappings
    }
```

## Future Extensions

### Automated Analysis Pipeline
- Parse all test JSON files to build comprehensive feature mapping
- Validate thesis coverage across entire test suite
- Identify gaps in Raft algorithm testing

### Enhanced Documentation
- Auto-generate cross-reference tables between tests and thesis sections
- Create visual maps of which tests cover which Raft concepts
- Generate coverage reports for Raft algorithm completeness

### Validation Framework
- Implement formal verification of Raft safety properties
- Add regression testing for Raft invariant maintenance
- Create property-based testing for Raft protocol compliance

This methodology provides a systematic foundation for understanding how the raftengine test suite validates Diego Ongaro's Raft consensus algorithm implementation.