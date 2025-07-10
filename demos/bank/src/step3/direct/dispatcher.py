from operator import methodcaller
from typing import Any
from base.json_helpers import bank_json_loads

class Dispatcher:

    def __init__(self, operations):
        self.operations = operations

    async def run_command(self, request) -> Any:
        rdict = bank_json_loads(request)
        callable_method = methodcaller(rdict['command_name'], **rdict['args'])
        res = await callable_method(self.operations)
        return res
        
