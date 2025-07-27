import json


# In this implementation, the names of the commands match the names of the methods they
# target, but there is no requirement for this. Use whatever scheme suit you

class Collector:
    """
    This class "collects" the method calls and their arguments into a serialized from that can
    later be presented to the matching Dispatcher class that converts them into method calls on
    a Counters class instance.

    This class needs to have the same method signatures as the Counters class, in so far
    as you intend to have those methods accessible from the client when you reach the client server
    stage.

    The 'pipe' argument to the __init__ method will be something that can take a serialized request
    and send it to the matching dispatcher somewhere, probably in a server. For local testing we
    can write a trivial pipe to connect the Collector and Dispatcher.
    
    """

    def __init__(self, pipe):
        self.pipe = pipe

    async def counter_add(self, name, value):
        package = dict(command_name="counter_add", args={'name': name, 'value': value})
        pstring = json.dumps(package)
        res = await self.pipe.run_command(pstring)
        return json.loads(res)

    async def get_counters(self):
        package = dict(command_name="get_counters", args={})
        pstring = json.dumps(package)
        res = await self.pipe.run_command(pstring)
        return json.loads(res)



