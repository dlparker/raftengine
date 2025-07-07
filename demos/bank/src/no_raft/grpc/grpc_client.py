#!/usr/bin/env python
"""gRPC Banking Client Test"""
import argparse
import asyncio
from pathlib  import Path
import sys
top_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(top_dir))
from src.no_raft.transports.grpc.client import get_grpc_client
from src.base.test_banking import test_banking


async def main():
    parser = argparse.ArgumentParser(description='gRPC Banking Client')
    parser.add_argument('--host', '-H', 
                       default='localhost',
                       help='Server host address (default: localhost)')
    parser.add_argument('--port', '-p', 
                       type=int, default=50051,
                       help='Server port (default: 50051)')
    
    args = parser.parse_args()
    
    print(f"=== gRPC Banking Client ===")
    print(f"Connecting to: {args.host}:{args.port}")
    
    client, cleanup = get_grpc_client(args.host, args.port)
    
    try:
        await test_banking(client)
    finally:
        if cleanup:
            if asyncio.iscoroutinefunction(cleanup):
                await cleanup()
            else:
                cleanup()

if __name__ == "__main__":
    asyncio.run(main())
