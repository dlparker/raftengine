from base.counters import Counters

class Demo:

    def __init__(self, counters):
        self.counters = counters

    async def do_fresh_demo(self):
        # this expects there to be no stored counters that have been reloaded, i.e. the counters are "fresh"
        print("getting non-existent counter 'a', should return 0")
        res = await self.counters.counter_add('a', 0)
        if res != 0:
            raise Exception(f"getting non-existent counter 'a' should have returned 0, not {res}")
        print(" => returned 0 as expected")
        print("adding +1 to 'a', should return 1")
        res = await self.counters.counter_add('a', 1)
        if res != 1:
            raise Exception(f"adding +1 to counter 'a' should have returned 1, not {res}")
        print(" => returned 1 as expected")
        print("adding -1 to 'a', should return 0")
        res = await self.counters.counter_add('a', -1)
        if res != 0:
            raise Exception(f"adding +1 to counter 'a' should have returned 0, not {res}")
        print(" => returned 0 as expected")
        print("getting non-existent counter 'b', should return 10")
        res = await self.counters.counter_add('b', 10)
        if res != 10:
            raise Exception(f"getting non-existent counter 'b' should have returned 10, not {res}")
        print(" => returned 10 as expected")
        
        print("getting all the counters")
        res = await self.counters.get_counters()
        if 'a' not in res or 'b' not in res:
            raise Exception(f"Getting all counters should have returned dictionary with keys 'a' and 'b', not {res}")
        print(f" => returned {res}")
        return res
    
    async def do_reload_demo(self, expected):
        # this expects there to be stored counters that have been reloaded that match the dict passed in
        for key in expected:
            print(f"getting restored counter '{key}', expecting {expected[key]}")
            res = await self.counters.counter_add(key, 0)
            if res != expected[key]:
                raise Exception(f"Error, got {res}")
        
        
