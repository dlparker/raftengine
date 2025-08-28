#!/usr/bin/env python
import asyncio
import argparse
from pathlib import Path
from raftengine.deck.log_control import LogController

log_controller = LogController.make_controller()
log_controller.set_default_level('warning')
log_controller.set_logger_level('Elections', 'info')

import sys
src_dir = Path(__file__).parent.parent
sys.path.insert(0, str(src_dir))

from ops.server_procs import main
if __name__=="__main__":
    import uvloop;
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    
    parser = argparse.ArgumentParser(description='Counters Raft Server')

    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument('--working_dir', '-w', 
                        help='Filesystem location of server working directory')
    group.add_argument('--base_dir', '-b', 
                        help='Filesystem location of where server working directory should be created')
    
    parser.add_argument('--join_uri', '-j', 
                        help='Server should join running cluster as provided uri')
    parser.add_argument('--cluster_uri', '-c', 
                        help='Server should join running cluster by contacting provided uri')

    group2 = parser.add_mutually_exclusive_group(required=False)
    group2.add_argument('-D', '--debug', action='store_true',
                       help="Set global logging level to debug")
    group2.add_argument('-I', '--info', action='store_true',
                       help="Set global logging level to info")
    group2.add_argument('-W', '--warning', action='store_true',
                       help="Set global logging level to warning")
    group2.add_argument('-E', '--error', action='store_true',
                       help="Set global logging level to error, which is the default")
    # Parse arguments
    args = parser.parse_args()

    if args.join_uri:
        if not args.cluster_uri:
            parser.error("must supply cluster uri with join uri")
        if args.base_dir is None:
            parser.error("must supply --base-dir with join uri")
        working_dir = Path(args.base_dir)
    elif args.cluster_uri:
        parser.error("must supply cluster uri with join uri")
    else:
        if args.working_dir is None:
            parser.error("must supply working directory if not using --join_uri")
        working_dir = Path(args.working_dir)
    if args.warning:
        log_controller.set_default_level('warning')
    elif args.info:
        log_controller.set_default_level('info')
    if args.debug:
        log_controller.set_default_level('debug')
    asyncio.run(main(working_dir, args.join_uri, args.cluster_uri))
