#!/usr/bin/env python3
"""
Script to rebuild protobuf files from banking.proto

This script regenerates the Python protobuf files (banking_pb2.py and banking_pb2_grpc.py)
from the banking.proto file. Run this after making changes to the proto file.

Usage:
    python rebuild_proto.py
    
Or make it executable and run:
    chmod +x rebuild_proto.py
    ./rebuild_proto.py
"""

import os
import sys
import subprocess
from pathlib import Path

def fix_grpc_imports(grpc_file):
    """Fix the import statement in the generated grpc file to use relative imports"""
    try:
        with open(grpc_file, 'r') as f:
            content = f.read()
        
        # Fix the import line
        fixed_content = content.replace(
            'import banking_pb2 as banking__pb2',
            'from . import banking_pb2 as banking__pb2'
        )
        
        if fixed_content != content:
            with open(grpc_file, 'w') as f:
                f.write(fixed_content)
            print("✓ Fixed import in banking_pb2_grpc.py")
        
    except Exception as e:
        print(f"⚠ Warning: Could not fix imports in {grpc_file}: {e}")

def main():
    # Get the directory containing this script
    script_dir = Path(__file__).parent
    proto_file = script_dir / "banking.proto"
    
    # Check if proto file exists
    if not proto_file.exists():
        print(f"Error: {proto_file} not found!")
        sys.exit(1)
    
    # Check if grpc_tools is available
    try:
        import grpc_tools.protoc
    except ImportError:
        print("Error: grpc_tools not installed. Install with: pip install grpcio-tools")
        sys.exit(1)
    
    print(f"Rebuilding protobuf files from {proto_file}")
    
    # Change to the grpc directory
    os.chdir(script_dir)
    
    # Run the protoc command
    cmd = [
        sys.executable, "-m", "grpc_tools.protoc",
        "-I.", 
        "--python_out=.",
        "--grpc_python_out=.",
        "banking.proto"
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print("✓ Successfully generated banking_pb2.py")
        print("✓ Successfully generated banking_pb2_grpc.py")
        
        # Check if files were created
        pb2_file = script_dir / "banking_pb2.py"
        pb2_grpc_file = script_dir / "banking_pb2_grpc.py"
        
        if pb2_file.exists() and pb2_grpc_file.exists():
            # Fix the import in the generated grpc file
            fix_grpc_imports(pb2_grpc_file)
            print(f"✓ Files created in {script_dir}")
        else:
            print("⚠ Warning: Expected files were not found after generation")
            
    except subprocess.CalledProcessError as e:
        print(f"Error running protoc: {e}")
        print(f"stdout: {e.stdout}")
        print(f"stderr: {e.stderr}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()