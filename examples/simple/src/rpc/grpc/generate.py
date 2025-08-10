#!/usr/bin/env python3
"""
Script to generate gRPC Python files from protobuf definitions.
Fixes import paths to work with the generated/ subdirectory structure.
"""

import os
import subprocess
import sys
from pathlib import Path

def run_command(cmd, cwd=None):
    """Run a shell command and return the result."""
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        sys.exit(1)
    return result.stdout

def fix_imports(file_path):
    """Fix import statements in generated gRPC files."""
    with open(file_path, 'r') as f:
        content = f.read()
    
    # The current setup uses sys.path manipulation to import directly,
    # so we need to keep the absolute import but make sure it works
    # No changes needed - the generated import should work with the sys.path setup
    
    with open(file_path, 'w') as f:
        f.write(content)

def main():
    # Get the directory where this script is located
    script_dir = Path(__file__).parent
    proto_file = script_dir / "raft_service.proto"
    generated_dir = script_dir / "generated"
    
    # Ensure generated directory exists
    generated_dir.mkdir(exist_ok=True)
    
    
    # Check if grpcio-tools is available
    try:
        import grpc_tools.protoc
    except ImportError:
        print("Error: grpcio-tools not found.")
        print("Please install it using: pip install grpcio-tools")
        sys.exit(1)
    
    print(f"Generating gRPC files from {proto_file}")
    
    # Generate the protobuf and gRPC files
    # Use python -m grpc_tools.protoc to ensure we use the installed version
    cmd = [
        sys.executable, '-m', 'grpc_tools.protoc',
        f'--proto_path={script_dir}',
        f'--python_out={generated_dir}',
        f'--grpc_python_out={generated_dir}',
        str(proto_file)
    ]
    
    run_command(cmd)
    
    # Fix imports in the generated gRPC file
    grpc_file = generated_dir / "raft_service_pb2_grpc.py"
    if grpc_file.exists():
        print(f"Fixing imports in {grpc_file}")
        fix_imports(grpc_file)
    
    # Ensure __init__.py exists
    init_file = generated_dir / "__init__.py"
    if not init_file.exists():
        init_file.write_text("")
    
    print("gRPC files generated successfully!")
    print(f"Generated files:")
    for file in generated_dir.glob("*.py"):
        print(f"  {file}")

if __name__ == "__main__":
    main()