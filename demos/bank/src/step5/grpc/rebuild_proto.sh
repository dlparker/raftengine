#!/bin/bash
# Alternative shell script to rebuild protobuf files

set -e  # Exit on any error

# Get the directory containing this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROTO_FILE="$SCRIPT_DIR/step5_banking.proto"

echo "Rebuilding protobuf files from $PROTO_FILE"

# Check if proto file exists
if [ ! -f "$PROTO_FILE" ]; then
    echo "Error: $PROTO_FILE not found!"
    exit 1
fi

# Change to the grpc directory
cd "$SCRIPT_DIR"

# Check if grpc_tools is available
if ! python -c "import grpc_tools.protoc" 2>/dev/null; then
    echo "Error: grpc_tools not installed. Install with: pip install grpcio-tools"
    exit 1
fi

# Run the protoc command
echo "Running protoc..."
python -m grpc_tools.protoc \
    -I. \
    --python_out=. \
    --grpc_python_out=. \
    step5_banking.proto

# Check if files were created
if [ -f "step5_banking_pb2.py" ] && [ -f "step5_banking_pb2_grpc.py" ]; then
    echo "✓ Successfully generated step5_banking_pb2.py"
    echo "✓ Successfully generated step5_banking_pb2_grpc.py"
    
    # Fix the import in the generated grpc file
    if [ -f "step5_banking_pb2_grpc.py" ]; then
        sed -i 's/import step5_banking_pb2 as step5__banking__pb2/from . import step5_banking_pb2 as step5__banking__pb2/' step5_banking_pb2_grpc.py
        echo "✓ Fixed import in step5_banking_pb2_grpc.py"
    fi
    
    echo "✓ Files created in $SCRIPT_DIR"
else
    echo "⚠ Warning: Expected files were not found after generation"
    exit 1
fi

echo "Done!"