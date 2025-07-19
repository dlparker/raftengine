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
from raftengine.deck.log_control import LogController
# setup LogControl before importing any modules that might initialize it first
LogController.controller = None
log_control = LogController.make_controller()

from base.demo_teller import demo_teller
from base.validate_teller import validate_teller
from base.operations import Teller
from base.collector import Collector
from base.dispatcher import Dispatcher
from base.fake_rpc_pipe import FakeRPCPipe
from base.proxy import TellerWrapper


async def main():
    parser = argparse.ArgumentParser(description='Run collector validation tests')
    parser.add_argument('mode', choices=['demo', 'test'], default='demo', nargs='?',
                        help='Choose between demo (user-friendly) or test (assertion-based) mode')
    parser.add_argument('--loops', type=int, default=1,
                        help='Number of test iterations to run (default: 1)')
    parser.add_argument('--random', action='store_true',
                        help='Use random data for names, addresses, and amounts')
    parser.add_argument('--no-timing', action='store_true',
                        help='Disable timing report (only for test mode)')
    parser.add_argument('--json-output', type=str, metavar='FILE',
                        help='Export timing statistics to JSON file')
    parser.add_argument('--delete_db',  action='store_true',
                        help='Delete target db before running')
    args = parser.parse_args()
    
    db_path = Path("/tmp/test_banking.db")
    if db_path.exists() and args.delete_db:
        db_path.unlink()
    teller = Teller(db_file=db_path)
    dispatcher = Dispatcher(teller)
    fake_pipe = FakeRPCPipe(dispatcher)
    collector = Collector(fake_pipe)
    
    if args.mode == 'demo':
        if args.loops > 1:
            for i in range(args.loops):
                print(f"\n=== Demo Run {i+1}/{args.loops} ===")
                await demo_teller(collector, use_random_data=args.random)
        else:
            await demo_teller(collector, use_random_data=args.random)
    else:
        # Prepare metadata for JSON export
        metadata = {
            'mode': 'test',
            'transport': 'collector',
            'loops': args.loops,
            'random_data': args.random,
            'db_path': str(db_path)
        }
        
        await validate_teller(collector, loops=args.loops, print_timing=not args.no_timing, 
                            json_output=args.json_output, metadata=metadata)
        if args.loops > 1:
            print(f"✓ All {args.loops} test iterations passed successfully!")
        else:
            print("✓ Test passed successfully!")

if __name__=="__main__":
    asyncio.run(main())
