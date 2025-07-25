import logging
import json
from collections import defaultdict
from raftengine.api.snapshot_api import SnapShot, SnapShotToolAPI

class DictTotalsOps: 

    def __init__(self, server):
        self.server = server
        self.log = server.log
        self.totals = defaultdict(int)
        self.snapshot = None
        self.snap_data = []
        
    async def process_command(self, command, serial):
        logger = logging.getLogger("DictTotalsOps")
        op, operand, value = command.split()
        if op not in ['add', 'sub']:
            error = "invalid command"
            logger.error("invalid command %s provided", op)
            return None, error
        if op == "add":
            self.totals[operand] += int(value)
        elif op == "sub":
            self.totals[operand] -= int(value)
        result = self.totals[operand]
        logger.debug("command %s returning %s for slot %s no error", command, result, operand)
        return result, None

    async def create_snapshot(self, index, term):
        self.snapshot = SnapShot(index, term)
        self.snapshot.tool = SnapShotTool(self, self.log, self.snapshot)
        self.snap_data = []
        for slot_name, slot_value in self.totals.items():
            self.snap_data.append({slot_name: slot_value})
        return self.snapshot

    async def begin_snapshot_import(self, snapshot) -> SnapShotToolAPI:
        self.snapshot = snapshot
        return SnapShotTool(self, self.log, self.snapshot)
    
    async def begin_snapshot_export(self, snapshot) -> SnapShot:
        self.snapshot = snapshot
        return SnapShotTool(self, self.log, self.snapshot)

class SnapShotTool(SnapShotToolAPI):

    def __init__(self, ops, log, snapshot=None):
        self.ops = ops
        self.log = log
        self.snapshot = None
        self.items_per_chunk = 2
        self.snapshot = snapshot

    async def load_snapshot_chunk(self, chunk):
        for item in json.loads(chunk):
            self.ops.totals.update(item)
    
    async def get_snapshot_chunk(self,  offset=0):
        done = False
        limit = offset + self.items_per_chunk
        if limit >= len(self.ops.snap_data):
            done = True
        data = json.dumps(self.ops.snap_data[offset:limit + 1])
        return data, limit + 1, done

    async def apply_snapshot(self):
        await self.log.install_snapshot(self.snapshot)


class SimpleOps: # pragma: no cover

    def __init__(self, server):
        self.server = server
        self.total = 0
        self.explode = False
        self.exploded = False
        self.return_error = False
        self.reported_error = False
        self.dump_state = False
        self.sleep_next_command = None  # If set, sleep for this many seconds on next process_command

    async def process_command(self, command, serial):
        import asyncio
        logger = logging.getLogger("SimpleOps")
        error = None
        result = None
        self.exploded = False
        
        # Handle sleep for timeout testing
        if self.sleep_next_command is not None:
            sleep_time = self.sleep_next_command
            self.sleep_next_command = None  # Reset after use
            logger.debug(f"SimpleOps sleeping for {sleep_time} seconds to force timeout")
            await asyncio.sleep(sleep_time)
        
        op, operand = command.split()
        if self.explode:
            #await asyncio.sleep(0.1)
            self.exploded = True
            raise Exception('boom!')
        if self.return_error:
            self.reported_error = True
            return None, "inserted error"
        if op not in ['add', 'sub']:
            error = "invalid command"
            logger.error("invalid command %s provided", op)
            return None, error
        if self.dump_state:
            await self.server.dump_log(0, -1)
            print(f'op {op} {operand} on total {self.total}')
        if op == "add":
            self.total += int(operand)
        elif op == "sub":
            self.total -= int(operand)
        result = self.total
        logger.debug("command %s returning %s no error", command, result)
        return result, None
