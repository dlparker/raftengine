#!/usr/bin/env python
from pathlib import Path
import sys
import os
import argparse
import shutil
from pprint import pprint
sdir = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(sdir))

from dev_tools.features import FeatureRegistry
from dev_tools.trace_output import TraceOutput

registry = FeatureRegistry.get_registry()

# Test file copy mapping from captures to docs
TEST_COPY_MAPPING = {
    'test_elections_1': 'docs/source/developer/tests/elections',
    'test_elections_2': 'docs/source/developer/tests/elections', 
    'test_commands_1': 'docs/source/developer/tests/commands',
    'test_partition_1': 'docs/source/developer/tests/partitions',
    'test_snapshots': 'docs/source/developer/tests/snapshots',
    'test_member_changes': 'docs/source/developer/tests/member_changes',
    'test_log_fiddles': 'docs/source/developer/tests/log_recovery',
    'test_class_edges': 'docs/source/developer/tests/edges',
    'test_msg_edges': 'docs/source/developer/tests/edges',
    'test_events': 'docs/source/developer/tests/events',
    'test_timers_1': 'docs/source/developer/tests/timers',
    'test_random_code': 'docs/source/developer/tests/random_code'
}

def copy_test_files_to_docs(verbose):
    """Copy generated test RST and PlantUML files to docs tree"""
    base_dir = Path(__file__).parent.parent.resolve()
    
    copied_files = []
    
    for test_path, docs_dir in TEST_COPY_MAPPING.items():
        # Copy RST files
        rst_source_dir = base_dir / "captures" / "test_traces" / "rst" / test_path
        rst_dest_dir = base_dir / docs_dir
        
        if rst_source_dir.exists():
            rst_dest_dir.mkdir(parents=True, exist_ok=True)
            for rst_file in rst_source_dir.glob("*.rst"):
                dest_file = rst_dest_dir / rst_file.name
                shutil.copy2(rst_file, dest_file)
                copied_files.append(str(dest_file.relative_to(base_dir)))
                if verbose:
                    print(f"Copied RST: {rst_file.name} -> {dest_file.relative_to(base_dir)}")
        
        # Copy PlantUML files
        puml_source_dir = base_dir / "captures" / "test_traces" / "plantuml" / test_path
        puml_dest_dir = base_dir / "docs" / "source" / "developer" / "tests" / "diagrams" / test_path
        
        if puml_source_dir.exists():
            puml_dest_dir.mkdir(parents=True, exist_ok=True)
            for puml_file in puml_source_dir.glob("*.puml"):
                dest_file = puml_dest_dir / puml_file.name
                shutil.copy2(puml_file, dest_file)
                copied_files.append(str(dest_file.relative_to(base_dir)))
                if verbose:
                    print(f"Copied PlantUML: {puml_file.name} -> {dest_file.relative_to(base_dir)}")
    
    if copied_files:
        print(f"Copied {len(copied_files)} files to docs tree")
    else:
        print("No files copied")
    
    return copied_files

def do_ops(copy_to_docs, verbose):
    tests = registry.feature_db.get_test_records()
    for test in tests:
        if verbose:
            print(f"{test['path']}, {test['name']}")
        jfilepath = TraceOutput.trace_file_path("json", test['path'], test['name'])
        if not jfilepath.exists():
            print("!"*120)
            print(f'file {jfilepath} not found!!!')
            print("!"*120)
            continue
        to = TraceOutput.from_json_file(jfilepath)
        to.write_org_file()
        to.write_org_file(include_legend=False)
        to.write_rst_file()
        to.write_csv_file()
        to.write_csv_file(digest=True)
        to.write_test_metadata_file()
        for section in registry.feature_db.get_test_section_records(test['path'], test['name']):
            try:
                to.write_section_puml_file(section['section_index'])
            except KeyError:
                print("!"*120)
                print(f"can't write puml file for section {section['section_index']} prolly no data")
                print("!"*120)
                continue
            if verbose:
                print(f"wrote puml for section {section['section_index']}")

        for tfm in registry.get_test_to_feature_maps():
            if tfm.test_id_path == Path(test['path']).stem  + '.' + test['name']:
                for ftmi in tfm.maps:
                    feature = registry.features[ftmi.feature]
                    branch = feature.branches[ftmi.branch]
                    registry.build_feature_branch_file(branch)
    
    # Optionally copy files to docs tree
    if copy_to_docs:
        print("\n" + "="*60)
        print("COPYING GENERATED FILES TO DOCS TREE")
        print("="*60)
        copied_files = copy_test_files_to_docs(verbose)
        
        if copied_files:
            print(f"\nSUCCESS: Copied {len(copied_files)} files to docs tree")
            if not verbose:
                print("Use --verbose to see individual file operations")
        else:
            print("\nNo files were copied")

def main():
    parser = argparse.ArgumentParser(description='Build documentation from test traces')
    parser.add_argument('--copy-to-docs', action='store_true', 
                       help='Copy generated RST and PlantUML files to docs tree')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Verbose output showing copied files')
    
    args = parser.parse_args()
    do_ops(args.copy_to_docs, args.verbose)
    
if __name__=="__main__":
    main()
