#!/usr/bin/env python
import asyncio
from pathlib import Path
import sys
src_dir = Path(__file__).parent.parent
logs_dir = Path(src_dir, 'logs')
sys.path.insert(0, str(logs_dir))
src_dir = Path(__file__).parent.parent
sys.path.insert(0, str(src_dir))

from raftengine.deck.log_control import LogController
log_controller = LogController.make_controller()
from ops.test_common import main, do_run_args, test_snapshots
from base.validator import Validator
from split_base.collector import Collector
    
class ValidatorRun:

    def __init__(self, collector, cluster_cli):
        self.collector = collector
        self.cluster_cli = cluster_cli
        self.vt = Validator(self.collector)
        
    async def run(self):
        res = await self.vt.do_test()

class SnapShotRun:

    def __init__(self, collector, cluster_cli):
        self.collector = collector
        self.cluster_cli = cluster_cli
        
    async def run(self):
        await test_snapshots(self.cluster_cli)

if __name__=="__main__":
    args = do_run_args()
    run_class_dict=dict(validator=ValidatorRun, snapshot=SnapShotRun)
    asyncio.run(main(args, run_class_dict))
