#!/usr/bin/env python3
"""
Script to generate gRPC Python code from banking.proto

Run this script to generate:
- banking_pb2.py (message classes)
- banking_pb2_grpc.py (service stubs and servers)

Usage:
    python generate_grpc.py
"""

import subprocess
import sys
from pathlib import Path

def main():
    # Get the directory containing this script
    script_dir = Path(__file__).parent
    proto_file = script_dir / "banking.proto"
    
    if not proto_file.exists():
        print(f"Error: {proto_file} not found")
        sys.exit(1)
    
    # Command to generate gRPC code
    cmd = [
        sys.executable, "-m", "grpc_tools.protoc",
        f"--proto_path={script_dir}",
        f"--python_out={script_dir}",
        f"--grpc_python_out={script_dir}",
        str(proto_file)
    ]
    
    print("Generating gRPC code...")
    print(f"Command: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print("✓ gRPC code generated successfully!")
        print(f"Generated files:")
        print(f"  - {script_dir}/banking_pb2.py")
        print(f"  - {script_dir}/banking_pb2_grpc.py")
        
        # Fix the import in banking_pb2_grpc.py for package-relative imports
        grpc_file = script_dir / "banking_pb2_grpc.py"
        if grpc_file.exists():
            print("Fixing imports in banking_pb2_grpc.py...")
            with open(grpc_file, 'r') as f:
                content = f.read()
            
            # Replace the problematic import
            content = content.replace(
                'import banking_pb2 as banking__pb2',
                'from . import banking_pb2 as banking__pb2'
            )
            
            with open(grpc_file, 'w') as f:
                f.write(content)
            print("✓ Fixed imports in banking_pb2_grpc.py")
        
        if result.stdout:
            print("Output:", result.stdout)
            
    except subprocess.CalledProcessError as e:
        print(f"Error generating gRPC code: {e}")
        if e.stdout:
            print("stdout:", e.stdout)
        if e.stderr:
            print("stderr:", e.stderr)
        print("\nMake sure grpcio-tools is installed:")
        print("pip install grpcio-tools")
        sys.exit(1)
    except FileNotFoundError:
        print("Error: grpc_tools.protoc not found")
        print("Make sure grpcio-tools is installed:")
        print("pip install grpcio-tools")
        sys.exit(1)

if __name__ == "__main__":
    main()