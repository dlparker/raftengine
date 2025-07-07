#!/usr/bin/env python
import argparse
import asyncio
from pathlib  import Path
import sys
top_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(top_dir))
from src.base.server import Server
from src.no_raft.transports.async_streams.proxy import  ASServer

async def main():
    parser = argparse.ArgumentParser(description='Async Streams Banking Server')
    parser.add_argument('--host', '-H', 
                       default='127.0.0.1',
                       help='Server host address (default: 127.0.0.1)')
    parser.add_argument('--port', '-p', 
                       type=int, default=9999,
                       help='Server port (default: 9999)')
    parser.add_argument('--database', '-d', 
                       default='banking_astream.db',
                       help='Database file path (default: banking_astream.db)')
    
    args = parser.parse_args()
    
    print(f"=== Async Streams Banking Server ===")
    print(f"Host: {args.host}")
    print(f"Port: {args.port}")
    print(f"Database: {args.database}")
    
    server = Server(db_file=args.database)
    as_server = ASServer(server, args.host, args.port)
    
    sock_server = await asyncio.start_server(
        as_server.handle_client, args.host, args.port)

    async with sock_server:
        await sock_server.serve_forever()

if __name__ == "__main__":
    asyncio.run(main())
      

