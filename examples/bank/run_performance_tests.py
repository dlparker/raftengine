#!/usr/bin/env python3
"""
Driver script to run performance validation tests with configurable loop count.
Results are stored in timestamped directories under timing_data/
"""

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

def create_timestamp_dir():
    """Create a timestamp directory that sorts chronologically with ls -lt"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_dir = Path("timing_data")
    base_dir.mkdir(exist_ok=True)
    
    timestamp_dir = base_dir / timestamp
    timestamp_dir.mkdir(exist_ok=True)
    return timestamp_dir

def run_command(cmd, cwd, output_dir):
    """Run a command in the specified directory"""
    print(f"Running: {cmd}")
    try:
        result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Command failed: {cmd}")
            print(f"stderr: {result.stderr}")
            return False
        print(f"✓ Command completed successfully")
        return True
    except Exception as e:
        print(f"Error running command: {e}")
        return False

def parse_transports(transport_arg):
    """Parse transport argument: single, comma-separated list, or 'all'"""
    available_transports = ['astream', 'aiozmq', 'fastapi', 'grpc']
    
    if transport_arg.lower() == 'all':
        return available_transports
    
    transports = [t.strip() for t in transport_arg.split(',')]
    
    # Validate each transport
    for transport in transports:
        if transport not in available_transports:
            raise ValueError(f"Invalid transport '{transport}'. Available: {', '.join(available_transports)}")
    
    return transports

def main():
    parser = argparse.ArgumentParser(
        description="Run performance validation tests",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Transport examples:
  %(prog)s 100 -t grpc                    # Test only gRPC
  %(prog)s 100 -t astream,grpc            # Test AsyncStream and gRPC
  %(prog)s 100 -t all                     # Test all transports
        """
    )
    parser.add_argument("loops", type=int, help="Number of loops to run for each test")
    parser.add_argument("-t", "--transport", 
                        required=True,
                        help="Transport types: single (grpc), comma-separated (astream,grpc), or 'all'")
    args = parser.parse_args()
    
    loops = args.loops
    
    try:
        selected_transports = parse_transports(args.transport)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
    
    # Create timestamped output directory
    output_dir = create_timestamp_dir()
    print(f"Results will be stored in: {output_dir}")
    print(f"Testing transports: {', '.join(selected_transports)}")
    
    # Change to src/cli directory
    cli_dir = Path("src/cli")
    if not cli_dir.exists():
        print("Error: src/cli directory not found")
        sys.exit(1)
    
    # Define commands with loop count substitution
    commands = [
        f"./validate_teller.py test --loops {loops} --json-output teller_{loops}_loops.json --delete_db",
        f"./validate_collector.py test --loops {loops} --json-output collector_{loops}_loops.json --delete_db",
    ]
    
    # Add RPC commands for selected transport types
    for transport in selected_transports:
        commands.append(f"./validate_rpc.py test --loops {loops} --json-output rpc_{transport}_{loops}_loops.json --delete_db -t {transport}")
    
    # Add Raft commands for selected transport types
    for transport in selected_transports:
        commands.append(f"./validate_raft.py test -t {transport} --loops {loops} --json-output raft_{transport}_{loops}_loops.json")
    
    success_count = 0
    total_commands = len(commands)
    
    for cmd in commands:
        if run_command(cmd, cli_dir, output_dir):
            success_count += 1
    
    # Move JSON files to output directory
    for json_file in cli_dir.glob("*_loops.json"):
        try:
            json_file.rename(output_dir / json_file.name)
            print(f"Moved {json_file.name} to {output_dir}")
        except Exception as e:
            print(f"Error moving {json_file.name}: {e}")
    
    print(f"\nCompleted {success_count}/{total_commands} commands successfully")
    print(f"Results stored in: {output_dir}")

if __name__ == "__main__":
    main()