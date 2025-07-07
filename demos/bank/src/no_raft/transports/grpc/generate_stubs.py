#!/usr/bin/env python3
"""
Script to regenerate gRPC stubs from the banking.proto file.

This script uses grpcio-tools to compile the protocol buffer definitions
into Python code. It generates both the message classes (banking_pb2.py)
and the gRPC service stubs (banking_pb2_grpc.py).

Usage:
    python generate_stubs.py
"""

import os
import subprocess
import sys
from pathlib import Path


def main():
    # Get the directory containing this script
    script_dir = Path(__file__).parent
    proto_file = script_dir / "banking.proto"
    
    if not proto_file.exists():
        print(f"Error: Proto file not found at {proto_file}")
        sys.exit(1)
    
    # Change to the grpc directory
    os.chdir(script_dir)
    
    # Command to generate the stubs
    cmd = [
        sys.executable, "-m", "grpc_tools.protoc",
        "--python_out=.",
        "--grpc_python_out=.",
        "--proto_path=.",
        "banking.proto"
    ]
    
    print(f"Running command: {' '.join(cmd)}")
    print(f"Working directory: {os.getcwd()}")
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print("✓ Successfully generated gRPC stubs")
        
        # Check if the files were created
        pb2_file = script_dir / "banking_pb2.py"
        grpc_file = script_dir / "banking_pb2_grpc.py"
        
        if pb2_file.exists():
            print(f"✓ Generated: {pb2_file}")
        else:
            print(f"✗ Missing: {pb2_file}")
            
        if grpc_file.exists():
            print(f"✓ Generated: {grpc_file}")
        else:
            print(f"✗ Missing: {grpc_file}")
            
    except subprocess.CalledProcessError as e:
        print(f"Error running protoc: {e}")
        print(f"stdout: {e.stdout}")
        print(f"stderr: {e.stderr}")
        sys.exit(1)
    except FileNotFoundError:
        print("Error: grpcio-tools not found. Install it with:")
        print("pip install grpcio-tools")
        sys.exit(1)


if __name__ == "__main__":
    main()