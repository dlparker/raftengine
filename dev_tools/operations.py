import logging
import json
from collections import defaultdict
from raftengine.api.snapshot_api import SnapShot, SnapshotToolAPI

class DictTotalsOps: 

    def __init__(self, server):
        self.server = server
        self.log = server.log
        self.totals = defaultdict(int)
        self.snapshot_tool = SnapshotTool(self, server.log)

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

    async def take_snapshot(self):
        return await self.snapshot_tool.take_snapshot()

class SnapshotTool(SnapshotToolAPI):

    def __init__(self, ops, log):
        self.ops = ops
        self.log = log
        self.snapshot = None
        self.data = []
        self.items_per_chunk = 2

    async def load_snapshot_chunk(self, snapshot, chunk):
        self.snapshot = snapshot
        for item in chunk:
            self.ops.totals.update(json.loads(item))
    
    async def get_snapshot_chunk(self, shapshot, offset=0):
        done = False
        limit = offset + self.items_per_chunk
        if limit >= len(self.data):
            done = True
        data = self.data[offset:limit + 1]
        return data, limit + 1, done

    async def apply_snapshot(self):
        return True

    # not part of the api, prolly not right place for it in realistic code, but works
    # here to simplify path for testing
    async def take_snapshot(self):
        last_index = await self.log.get_last_index()
        last_term = await self.log.get_last_term()
        self.snapshot = SnapShot(last_index, last_term, self)
        for slot_name, slot_value in self.ops.totals.items():
            self.data.append(json.dumps({slot_name: slot_value}))
        return self.snapshot

class SimpleOps: # pragma: no cover

    def __init__(self, server):
        self.server = server
        self.total = 0
        self.explode = False
        self.exploded = False
        self.return_error = False
        self.reported_error = False
        self.dump_state = False

    async def process_command(self, command, serial):
        logger = logging.getLogger("SimpleOps")
        error = None
        result = None
        self.exploded = False
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
