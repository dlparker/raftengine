from base.counters import Counters

class Demo:

    def __init__(self, counters):
        self.counters = counters
    
    async def do_reload_demo(self, expected):
        # this expects there to be stored counters that have been reloaded that match the dict passed in
        for key in expected:
            print(f"getting restored counter '{key}', expecting {expected[key]}")
            res = await self.counters.counter_add(key, 0)
            if res != expected[key]:
                raise Exception(f"Error, got {res}")
        
    async def do_unknown_state_demo(self):
        local_values = {}
        for name in ['a', 'b', 'c', 'd', 'e', 'f']:
            print(f"getting counter {name}")
            first_value = local_values[name] = await self.counters.counter_add(name, 0)
            print(f"adding +3 to {name}, should return {local_values[name] + 3}")
            res = await self.counters.counter_add(name, 3)
            if res != local_values[name] + 3:
                raise Exception(f"adding +3 to counter {name} should have returned {local_values[name] + 3}, not {res}")
            local_values[name] = res
            print(f" => returned {local_values[name]} as expected")
            print(f"adding -2 to {name}, should return {first_value +1}")
            res = await self.counters.counter_add(name, -2)
            if res != first_value + 1: 
                raise Exception(f"adding +1 to counter {name} should have returned {first_value +1}, not {res}")
        
        print("getting all the counters")
        res = await self.counters.get_counters()
        if 'a' not in res or 'b' not in res:
            raise Exception(f"Getting all counters should have returned dictionary with keys 'a' and 'b', not {res}")
        print(f" => returned {res}")
        return res
