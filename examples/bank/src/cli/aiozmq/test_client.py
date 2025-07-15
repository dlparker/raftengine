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
from cli.test_client_common import validate, add_common_arguments
from tx_aiozmq.rpc_client import RPCClient

async def main():
    parser = argparse.ArgumentParser(
        description='Raft Banking ZeroMQ validator client')
    
    parser.add_argument('--port', '-p', type=int, default=50150,
                        help='port for leader node, default=50150')
    
    # Add common validation arguments
    add_common_arguments(parser)
    
    args = parser.parse_args()
    
    port = args.port
    rpc_client = RPCClient('localhost', port)
    await validate(rpc_client, 
                  mode=args.mode,
                  loops=args.loops,
                  use_random_data=args.random,
                  print_timing=not args.no_timing,
                  json_output=args.json_output,
                  check_raft_message=args.check_raft)

if __name__=="__main__":
    asyncio.run(main())
