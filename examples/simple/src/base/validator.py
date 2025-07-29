import string
from base.counters import Counters

class Validator:

    def __init__(self, counters):
        self.counters = counters

    async def do_test(self):
        orig = {}
        mod = {}
        for key in string.ascii_letters:
            orig[key] = await self.counters.counter_add(key, 0)

        res = await self.counters.get_counters()
        for key in string.ascii_letters:
            assert key in res
            assert res[key] == orig[key]
            mod[key] = await self.counters.counter_add(key, 1)
            assert mod[key] == orig[key] + 1
        mod_res = await self.counters.get_counters()
        for key in string.ascii_letters:
            assert mod_res[key] == mod[key] 
        print
