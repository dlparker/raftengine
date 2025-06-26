#!/usr/bin/env python
from pathlib import Path
import os
import sys
from pprint import pprint

os.environ['PYTHONBREAKPOINT'] = "ipdb.set_trace"
os.environ['PYTHONPATH'] = "."

from dev_tools.trace_data import SaveEvent
from dev_tools.trace_output import TraceOutput
from dev_tools.trace_shorthand import Shorthand, ShorthandType1, NodeStateShortestFormat

def test_formatters_for_test(test_file_part, test_name_part):
    """Test formatters for a specific test"""
    print(f"\n=== Testing formatters for {test_file_part}::{test_name_part} ===")
    
    target_test = f"tests/{test_file_part}.py::{test_name_part}"
    json_path = Path(f'captures/test_traces/json/{test_file_part}/{test_name_part}.json')
    org_path = Path(f'captures/test_traces/no_legend_org/{test_file_part}/{test_name_part}.org')
    
    # Check if files exist
    if not json_path.exists():
        print(f"JSON file not found: {json_path}")
        return
    if not org_path.exists():
        print(f"ORG file not found: {org_path}")
        return
        
    to = TraceOutput.from_json_file(json_path)
    
    message_types_found = set()
    state_history = {}
    
    for line in to.test_data.trace_lines:
        for node_index, ns in enumerate(line):
            if ns.save_event == SaveEvent.message_op and ns.message:
                if isinstance(ns.message, dict):
                    code = ns.message['code']
                else:
                    code = ns.message.code
                message_types_found.add(code)
                
                prev_state = state_history.get(node_index, None)
                nsf = NodeStateShortestFormat(ns, prev_state)
                data = nsf.format()
                
                # Extract just the op part for comparison
                if data['op'] and data['op'] != 'null':
                    print(f"Message type: {code:20} | Formatted: {data['op']}")
            
            state_history[node_index] = ns
    
    print(f"Message types found in this test: {sorted(message_types_found)}")
    return message_types_found

if __name__ == "__main__":
    # Test different message types
    test_cases = [
        ("test_elections_1", "test_pre_election_1"),  # pre-vote messages
        ("test_elections_2", "test_election_candidate_log_too_old_1"),  # vote messages  
        ("test_member_changes", "test_add_follower_too_many_rounds_1"),  # membership changes
        ("test_elections_2", "test_power_transfer_1"),  # power transfer
    ]
    
    all_message_types = set()
    
    for test_file, test_name in test_cases:
        found_types = test_formatters_for_test(test_file, test_name)
        if found_types:
            all_message_types.update(found_types)
    
    print(f"\n=== Summary ===")
    print(f"All message types found across tests: {sorted(all_message_types)}")