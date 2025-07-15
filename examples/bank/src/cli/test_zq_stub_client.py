#!/usr/bin/env python
import asyncio
import argparse
from pathlib import Path
import sys
this_dir = Path(__file__).resolve().parent
for parent in this_dir.parents:
    if parent.name == 'src':
        if parent not in sys.path:
            sys.path.insert(0, str(parent))
            break
else:
    raise ImportError("Could not find 'src' directory in the path hierarchy")
from cli.stub_client_common import validate
from tx_aiozmq.rpc_client import RPCClient

async def main():
    parser = argparse.ArgumentParser(
        description='Raft Banking FastAPI validator client')
    
    parser.add_argument('--port', '-p', type=int, default=50061,
                        help='port for leader node, default=50061')
    
    args = parser.parse_args()
    
    port = args.port
    rpc_client = RPCClient('localhost', port)
    await validate(rpc_client)

if __name__=="__main__":
    asyncio.run(main())
