#!/usr/bin/env python
"""gRPC Banking Server"""
import argparse
import time
from pathlib  import Path
import sys
top_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(top_dir))
from src.base.server import Server
from src.transports.grpc.server import serve_banking_server


def main():
    """Start the gRPC banking server"""
    parser = argparse.ArgumentParser(description='gRPC Banking Server')
    parser.add_argument('--port', '-p', 
                       type=int, default=50051,
                       help='Server port (default: 50051)')
    parser.add_argument('--database', '-d', 
                       default='banking_grpc.db',
                       help='Database file path (default: banking_grpc.db)')
    
    args = parser.parse_args()
    
    print(f"=== gRPC Banking Server ===")
    print(f"Port: {args.port}")
    print(f"Database: {args.database}")
    
    server = Server(db_file=args.database)
    grpc_server = serve_banking_server(server, port=args.port)
    
    try:
        while True:
            time.sleep(86400)  # Keep running
    except KeyboardInterrupt:
        print("Shutting down gRPC server...")
        grpc_server.stop(0)


if __name__ == "__main__":
    main()
