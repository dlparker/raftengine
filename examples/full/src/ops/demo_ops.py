#!/usr/bin/env python
import asyncio
from pathlib import Path
import sys
import time
import json
import argparse
import pickle
import traceback
src_dir = Path(__file__).parent.parent
sys.path.insert(0, str(src_dir))
from raftengine.deck.log_control import LogController
log_controller = LogController.make_controller()
from split_base.collector import Collector
from base.demo import Demo
from ops.test_common import main, do_run_args

class DemoRun:
    
    def __init__(self, collector, cluster_cli):
        self.collector = collector
        self.cluster_cli = cluster_cli
        self.demo = Demo(self.collector)
        
    async def run(self):
        res = await self.demo.do_unknown_state_demo()
    
if __name__=="__main__":
    args = do_run_args()
    run_class_dict=dict(demo=DemoRun)
    asyncio.run(main(args, run_class_dict))
