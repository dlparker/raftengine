#!/usr/bin/env python
import argparse
import asyncio
from pathlib  import Path
import sys
top_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(top_dir))
from src.base.client import Client
from src.transports.astream.proxy import ASClient, ServerProxy
from src.systems.direct.one_process import test_banking

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
    
    as_client = ASClient(args.host, args.port)
    proxy = ServerProxy(as_client)
    client = Client(proxy)
    
    try:
        await test_banking(client)
    finally:
        await as_client.close()

if __name__ == "__main__":
    asyncio.run(main())
      

