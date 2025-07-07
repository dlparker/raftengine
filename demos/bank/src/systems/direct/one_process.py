#!/usr/bin/env python
import argparse
import asyncio
from pathlib  import Path
import sys
top_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(top_dir))
from src.systems.get_client import get_direct_client
from src.systems.test_banking import test_banking
    
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
      

