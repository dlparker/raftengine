#!/usr/bin/env python
"""Raft-enabled gRPC Banking Client Test"""
import argparse
import asyncio
from pathlib  import Path
import sys
top_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(top_dir))
from src.raft_prep.transports.grpc.client import get_grpc_client
from src.base.test_banking import test_banking


async def main():
    parser = argparse.ArgumentParser(description='Raft-enabled gRPC Banking Client')
    parser.add_argument('--host', '-H', 
                       default='localhost',
                       help='Server host address (default: localhost)')
    parser.add_argument('--port', '-p', 
                       type=int, default=50051,
                       help='Server port (default: 50051)')
    
    args = parser.parse_args()
    
    print(f"=== Raft-enabled gRPC Banking Client ===")
    print(f"Connecting to: {args.host}:{args.port}")
    
    client, cleanup = get_grpc_client(args.host, args.port)
    
    try:
        # Test banking operations
        await test_banking(client)
        
        # Test Raft message functionality
        print("\n=== Testing Raft Message ===")
        test_message = {
            "message_type": "TestMessage",
            "message_data": "Hello from Raft client!"
        }
        response = await client.raft_message(test_message)
        print(f"Sent: {test_message}")
        print(f"Received: {response}")
        
    finally:
        if cleanup:
            if asyncio.iscoroutinefunction(cleanup):
                await cleanup()
            else:
                cleanup()


if __name__ == "__main__":
    asyncio.run(main())