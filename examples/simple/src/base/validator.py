from base.counters import Counters

class Validator:

    def __init__(self, counters):
        self.counters = counters

    async def do_test(self, expected=None):
        if not expected:
            assert await self.counters.counter_add('a', 0) == 0
            assert await self.counters.counter_add('a', 1) == 1
            assert await self.counters.counter_add('a', -1) == 0
            assert await self.counters.counter_add('b', 10) == 10
            res = await self.counters.get_counters()
            assert len(res) == 2
            assert res['a'] == 0
            assert res['b'] == 10
            return res
        else:
            for key in expected:
                res = await self.counters.counter_add(key, 0)
                assert res == expected[key]
            return None
        
