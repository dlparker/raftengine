#!/usr/bin/env python
import argparse
import asyncio
from pathlib  import Path
import sys
top_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(top_dir))
from src.base.server import Server

from src.base.client import Client
from src.base.server import Server

top_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(top_dir))
from src.base.test_banking import test_banking

def get_direct_client(database_file: str):
    """Create a direct client that bypasses any proxy/transport layer"""
    server = Server(db_file=database_file)
    client = Client(server)
    def fake():
        pass
    return client, fake  # No cleanup needed
async def main():
    parser = argparse.ArgumentParser(description='Direct Banking Demo')
    parser.add_argument('--database', '-d', 
                       default='banking_direct.db',
                       help='Database file path (default: banking_direct.db)')
    
    args = parser.parse_args()
    
    print(f"=== Direct Banking Demo ===")
    print(f"Database: {args.database}")
    
    client, cleanup = get_direct_client(args.database)
    
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


