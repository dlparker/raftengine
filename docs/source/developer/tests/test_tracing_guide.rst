Test Tracing Developer Guide
=============================

This guide provides step-by-step instructions for developers on how to work with the comprehensive test tracing system in Raftengine. The tracing system captures detailed execution data from tests and generates documentation in multiple formats.

Overview
--------

The test tracing system:

- **Captures** detailed execution traces from tests
- **Generates** documentation in multiple formats (RST, CSV, JSON, PlantUML)
- **Maps** test behaviors to Raft consensus algorithm features
- **Provides** visualization through sequence diagrams and data tables

Key Components
--------------

**Test Infrastructure:**
- ``cluster.test_trace`` - Main tracing interface in tests
- ``FeatureRegistry`` - Maps test behaviors to Raft features
- ``TestSection`` - Organizes test execution into logical sections

**Generated Files:**
- **JSON**: Complete trace data (``captures/test_traces/json/``)
- **Metadata**: Test structure without trace data (``captures/test_traces/metadata/``)
- **CSV**: Filtered trace events (``captures/test_traces/digest_csv/``)
- **RST**: Documentation format (``captures/test_traces/rst/``)
- **PlantUML**: Sequence diagrams (``captures/test_traces/plantuml/``)

Step 1: Adding Test Definitions
-------------------------------

When creating a new test, follow these patterns:

Basic Test Structure
^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    from dev_tools.features import FeatureRegistry
    
    registry = FeatureRegistry.get_registry()
    
    async def test_my_new_test(cluster_maker):
        """
        Brief description of what this test validates.
        
        Detailed explanation of the test scenario, including:
        - What Raft behaviors are being tested
        - The sequence of operations
        - Expected outcomes
        """
        cluster = cluster_maker(3)
        cluster.set_configs()
        
        # Define the test and get logger
        logger = logging.getLogger("test_code")
        await cluster.test_trace.define_test("Clear description of test purpose", logger=logger)

Required Imports
^^^^^^^^^^^^^^^^

.. code-block:: python

    import asyncio
    import logging
    from dev_tools.features import FeatureRegistry
    from dev_tools.pausing_cluster import PausingCluster, cluster_maker

Step 2: Adding Section Definitions
----------------------------------

Organize your test into logical sections using ``start_test_prep`` and ``start_subtest``:

Test Preparation Section
^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    await cluster.test_trace.start_test_prep("Setup description")
    # Setup code (elections, initial state, etc.)

Test Subsections
^^^^^^^^^^^^^^^^

.. code-block:: python

    await cluster.test_trace.start_subtest("Section description")
    # Test logic for this specific behavior
    
    await cluster.test_trace.start_subtest("Another section")
    # More test logic
    
    # End the final section (optional but recommended)
    await cluster.test_trace.end_subtest()

Section Guidelines
^^^^^^^^^^^^^^^^^^

- **Preparation sections**: Use for setup (elections, configuration)
- **Test sections**: Use for behaviors being validated
- **Descriptive names**: Use clear, specific descriptions
- **Logical grouping**: Group related operations together

Step 3: Adding Feature Definitions
----------------------------------

Map your test sections to Raft features using the feature registry:

Basic Feature Mapping
^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    # For features being used for setup
    registry.get_raft_feature("leader_election.all_yes_votes.with_pre_vote", "uses")
    
    # For features being explicitly tested
    registry.get_raft_feature("state_machine_command.request_redirect", "tests")

Feature Naming Convention
^^^^^^^^^^^^^^^^^^^^^^^^^

Features use dot notation: ``{primary_feature}.{scenario_branch}``

**Primary Features:**
- ``leader_election`` - Leader election behaviors
- ``log_replication`` - Log replication and synchronization
- ``state_machine_command`` - Client command processing
- ``network_partition`` - Network partition handling
- ``membership_changes`` - Cluster configuration changes

**Example Feature Branches:**
- ``leader_election.all_yes_votes.with_pre_vote``
- ``state_machine_command.request_redirect``
- ``log_replication.follower_recovery_catchup``

Step 4: Creating Feature Branch Definitions
-------------------------------------------

If your test uses new features that don't exist, create feature definition files:

Directory Structure
^^^^^^^^^^^^^^^^^^^

.. code-block::

    docs/source/developer/tests/features/
    ├── {primary_feature}/
    │   ├── features.rst
    │   ├── narative.rst
    │   ├── short.rst
    │   └── branches/
    │       └── {branch_name}/
    │           ├── features.rst
    │           ├── narative.rst
    │           └── short.rst

Required Files for Each Feature Branch
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**short.rst** - One-line description:

.. code-block:: rst

    Commands sent to candidates return retry response

**narative.rst** - Detailed explanation:

.. code-block:: rst

    When a client sends a command request to a node that is currently in the 
    CANDIDATE role (during an election), the node should respond with a retry 
    indication rather than processing the command. This is because candidates 
    are not authorized to process client commands - only leaders can do that.
    
    The retry response indicates that the cluster is temporarily unavailable 
    for command processing due to an ongoing election, and the client should 
    retry the request later once a leader has been elected.

**features.rst** - Documentation structure:

.. code-block:: rst

    State Machine Command: Retry During Election
    ============================================
    
    .. include:: narative.rst
    
    Tests Using This Feature
    -------------------------
    
    This feature is used by tests that verify proper command rejection during elections:
    
    .. include:: short.rst

Step 5: Running the Documentation Builder
-----------------------------------------

Generate all trace documentation using the build script:

Basic Usage
^^^^^^^^^^^

.. code-block:: bash

    # Generate documentation only
    python dev_tools/build_docs.py
    
    # Generate documentation AND copy to docs tree
    python dev_tools/build_docs.py --copy-to-docs
    
    # With verbose output showing copied files
    python dev_tools/build_docs.py --copy-to-docs --verbose

What Gets Generated
^^^^^^^^^^^^^^^^^^^

The build process creates:

- **JSON traces**: Complete execution data for debugging
- **Metadata files**: Test structure without trace data (97% smaller)
- **Digest CSV**: Filtered events with original line indices
- **RST documentation**: Human-readable test documentation
- **PlantUML diagrams**: Sequence diagrams for each test section

File Locations
^^^^^^^^^^^^^^

.. code-block::

    captures/test_traces/
    ├── json/{test_path}/{test_name}.json          # Complete trace data
    ├── metadata/{test_path}/{test_name}.json      # Test structure only
    ├── digest_csv/{test_path}/{test_name}.csv     # Filtered events
    ├── rst/{test_path}/{test_name}.rst            # Documentation
    └── plantuml/{test_path}/{test_name}_N.puml    # Sequence diagrams

Step 6: Finding and Using Generated Files
-----------------------------------------

Locating Your Test's Trace Files
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

For a test ``test_my_feature`` in file ``tests/test_commands_2.py``:

.. code-block::

    captures/test_traces/
    ├── json/test_commands_2/test_my_feature.json
    ├── metadata/test_commands_2/test_my_feature.json
    ├── digest_csv/test_commands_2/test_my_feature.csv
    ├── rst/test_commands_2/test_my_feature.rst
    └── plantuml/test_commands_2/test_my_feature_1.puml (one per section)

Using Trace Data for Analysis
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**For feature analysis** (recommended):

.. code-block:: python

    import json
    import pandas as pd
    
    # Load lightweight metadata
    with open('captures/test_traces/metadata/test_commands_1/test_command_1.json') as f:
        metadata = json.load(f)
    
    # Load filtered trace events
    df = pd.read_csv('captures/test_traces/digest_csv/test_commands_1/test_command_1.csv')
    
    # Correlate events with test sections using original_line_index
    for section_id, section in metadata['test_sections'].items():
        section_events = df[
            (df['original_line_index'] >= section['start_pos']) & 
            (df['original_line_index'] <= section['end_pos'])
        ]

**For debugging** (when needed):

.. code-block:: python

    # Load complete trace data (large file)
    with open('captures/test_traces/json/test_commands_1/test_command_1.json') as f:
        full_trace = json.load(f)

Step 7: Adding Generated Documentation to Test Docs
---------------------------------------------------

File Copy Mapping
^^^^^^^^^^^^^^^^^^

The ``--copy-to-docs`` flag automatically copies files according to this mapping:

.. list-table:: Test Documentation Locations
   :header-rows: 1
   :widths: 30 40

   * - Test File
     - Documentation Directory
   * - ``test_elections_1.py``
     - ``docs/source/developer/tests/elections/``
   * - ``test_commands_1.py``
     - ``docs/source/developer/tests/commands/``
   * - ``test_snapshots.py``
     - ``docs/source/developer/tests/snapshots/``
   * - ``test_member_changes.py``
     - ``docs/source/developer/tests/member_changes/``

Manual Integration
^^^^^^^^^^^^^^^^^^

If you need to manually add a test's documentation:

1. **Copy RST file**:
   
   .. code-block:: bash
   
       cp captures/test_traces/rst/test_commands_1/test_my_feature.rst \\
          docs/source/developer/tests/commands/

2. **Copy PlantUML diagrams**:
   
   .. code-block:: bash
   
       cp captures/test_traces/plantuml/test_commands_1/test_my_feature_*.puml \\
          docs/source/developer/tests/diagrams/test_commands_1/

3. **Update index file** (if needed):
   
   Add your test to the appropriate ``index.rst`` file in the target directory.

Complete Example
----------------

Here's a complete example of a properly instrumented test:

.. code-block:: python

    async def test_leader_isolation_recovery(cluster_maker):
        """
        Test leader recovery after network partition isolation.
        
        This test validates that when a leader becomes isolated from the 
        cluster and a new leader is elected, the original leader properly 
        steps down when the partition heals and accepts the new leader.
        """
        cluster = cluster_maker(3)
        cluster.set_configs()
        
        uri_1, uri_2, uri_3 = cluster.node_uris
        ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]
        logger = logging.getLogger("test_code")
        
        # Define test
        await cluster.test_trace.define_test(
            "Leader isolation and recovery behavior", 
            logger=logger
        )
        
        # Section 1: Setup - elect initial leader
        await cluster.test_trace.start_test_prep("Initial leader election")
        registry.get_raft_feature("leader_election.all_yes_votes.with_pre_vote", "uses")
        await cluster.start()
        await ts_3.start_campaign()
        sequence = SNormalElection(cluster, 1)
        await cluster.run_sequence(sequence)
        assert ts_3.get_role_name() == "LEADER"
        
        # Section 2: Test - isolate leader
        await cluster.test_trace.start_subtest("Isolate current leader")
        registry.get_raft_feature("network_partition.leader_isolation", "tests")
        await cluster.partition_node(uri_3)
        
        # Section 3: Test - new election
        await cluster.test_trace.start_subtest("New leader election")
        registry.get_raft_feature("leader_election.post_partition", "tests")
        await ts_1.start_campaign()
        sequence = SPartialElection(cluster, voters=[uri_1, uri_2])
        await cluster.run_sequence(sequence)
        assert ts_1.get_role_name() == "LEADER"
        
        # Section 4: Test - partition recovery
        await cluster.test_trace.start_subtest("Partition healing and leader step-down")
        registry.get_raft_feature("leader_election.step_down_on_higher_term", "tests")
        await cluster.heal_partition()
        await cluster.deliver_all_pending()
        assert ts_3.get_role_name() == "FOLLOWER"
        assert ts_3.get_leader_uri() == uri_1
        
        await cluster.test_trace.end_subtest()

Next Steps
----------

After creating your test:

1. **Run the test** to generate trace data:
   
   .. code-block:: bash
   
       ./run_tests.sh tests/test_my_file.py::test_my_feature

2. **Generate documentation**:
   
   .. code-block:: bash
   
       python dev_tools/build_docs.py --copy-to-docs

3. **Review generated files** in the appropriate docs directories

4. **Create feature definitions** for any new features used

5. **Update feature mappings** in ``docs/source/developer/tests/features_in_tests.rst``

Best Practices
--------------

**Test Organization:**
- Use clear, descriptive section names
- Group related operations logically
- Include both setup and validation sections

**Feature Mapping:**
- Mark features as "uses" when they're for setup
- Mark features as "tests" when they're being validated
- Create new feature definitions for novel behaviors

**Documentation:**
- Write detailed test docstrings
- Use meaningful section descriptions
- Include references to Raft thesis sections when relevant

**File Management:**
- Use the ``--copy-to-docs`` flag for automated copying
- Review generated RST files before committing
- Keep feature definitions up to date

Troubleshooting
---------------

**Common Issues:**

1. **Missing trace files**: Ensure test completed successfully and feature registry was used
2. **Empty sections**: Check that test sections have actual operations
3. **Build errors**: Verify all required feature definitions exist
4. **Large files**: Use metadata + CSV approach for analysis instead of full JSON

**Getting Help:**

- Check existing tests for examples
- Review generated trace files for debugging
- Use verbose output to see detailed file operations
- Examine the feature registry database for existing mappings