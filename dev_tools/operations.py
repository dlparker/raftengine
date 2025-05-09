import logging
from collections import defaultdict
from raftengine.api.snapshot_api import SnapShotAPI, SnapToolAPI

class DictTotalsOps: 

    def __init__(self, server):
        self.server = server
        self.totals = defaultdict(int)
        self.tool = SnapTool(self)

    def get_snapshot_tool(self, log):
        self.tool.set_log(log)
        return self.tool
    
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

    async def fill_snapshot(self, snapshot):
        for slot_name, slot_value in self.totals.items():
            await snapshot.add_data_item({slot_name: slot_value})

    async def unpack_snapshot_data_item(self, item):
        self.totals.update(item)

    
class SnapTool(SnapToolAPI):

    def __init__(self, ops):
        self.ops = ops
        self.log = None
        self.snapshot = None

    def set_log(self, log):
        self.log = log

    async def take_snapshot(self):
        last_index,last_term = await self.log.start_snapshot()
        ss = SnapShot(last_index, last_term)
        await self.ops.fill_snapshot(ss)
        return ss
    
    async def start_snapshot_load(self, last_index, last_term, first_chunk):
        self.snapshot = SnapShot(last_index, last_term)
        for item in first_chunk:
            await self.ops.unpack_snapshot_data_item(item)
        
    async def continue_snapshot_load(self, chunk, offset, done):
        for item in chunk:
            await self.ops.unpack_snapshot_data_item(item)
        if done:
            await self.log.install_snapshot(self.snapshot)
        
    
class SnapShot(SnapShotAPI):

    def __init__(self, last_index, last_term):
        self.last_index = last_index
        self.last_term = last_term
        self.data = []
        self.items_per_chunk = 2

    def get_last_index(self):
        return self.last_index
    
    def get_last_term(self):
        return self.last_term

    async def add_data_item(self, item):
        self.data.append(item)


    async def get_chunk(self, offset=0):
        done = False
        limit = offset + self.items_per_chunk
        if limit >= len(self.data):
            done = True
        data = self.data[offset:limit + 1]
        return data, limit + 1, done

    async def save_chunk(self, data, offset=0):
        if len(self.data) != offset:
            raise Exception('cannot store data out of order')
        self.data.extend(data)

        
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
