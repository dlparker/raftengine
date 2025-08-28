from operator import methodcaller
import json
import traceback

class Dispatcher:

    def __init__(self, counters):
        self.counters = counters

    async def route_command(self, packed):
        package = json.loads(packed)
        kwargs = package['args']
        callable_method = methodcaller(package['command_name'], **kwargs)
        result = await callable_method(self.counters)
        return json.dumps(result)
