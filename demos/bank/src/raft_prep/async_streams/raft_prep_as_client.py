#!/usr/bin/env python
import argparse
import asyncio
from pathlib  import Path
import sys
top_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(top_dir))
from src.raft_prep.transports.async_streams.proxy import get_astream_client
from src.base.test_banking import test_banking

async def main():
    parser = argparse.ArgumentParser(description='Async Streams Banking Client')
    parser.add_argument('--host', '-H', 
                       default='localhost',
                       help='Server host address (default: localhost)')
    parser.add_argument('--port', '-p', 
                       type=int, default=9999,
                       help='Server port (default: 9999)')
    
    args = parser.parse_args()
    
    print(f"=== Async Streams Banking Client ===")
    print(f"Connecting to: {args.host}:{args.port}")
    
    client, cleanup = get_astream_client(args.host, args.port)
    
    try:
        await test_banking(client)
        print(await client.raft_message("{'foo': 'bar'}"))
    finally:
        if cleanup:
            if asyncio.iscoroutinefunction(cleanup):
                await cleanup()
            else:
                cleanup()

if __name__ == "__main__":
    asyncio.run(main())
      

