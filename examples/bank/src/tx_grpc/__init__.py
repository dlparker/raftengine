# gRPC transport implementation for banking service

# Re-export generated gRPC modules for consistent imports
try:
    from .banking_pb2 import *
    from .banking_pb2_grpc import *
except ImportError:
    print("gRPC generated files not found. Run generate_grpc.py first.")
    print("python src/tx_grpc/generate_grpc.py")
    raise