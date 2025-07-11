import logging
from operator import methodcaller
from typing import Any
from base.json_helpers import bank_json_loads, bank_json_dumps
logger = logging.getLogger(__name__)

class Dispatcher:

    def __init__(self, operations):
        self.operations = operations

    async def run_command(self, request) -> Any:
        rdict = bank_json_loads(request)
        callable_method = methodcaller(rdict['command_name'], **rdict['args'])
        logger.debug(f"Dispatching {rdict['command_name']}")
        res = await callable_method(self.operations)
        # in this setup, we need to serialize result, normally you wouldn't
        return bank_json_dumps(res)
        
