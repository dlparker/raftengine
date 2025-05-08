import logging
from collections import defaultdict
from raftengine.api.snapshot_api import SnapShot

class DictTotalsOps: 

    def __init__(self, server):
        self.server = server
        self.totals = defaultdict(int)

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
