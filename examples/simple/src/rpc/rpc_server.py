import aiozmq.rpc

class RPCServer(aiozmq.rpc.AttrHandler):

    def __init__(self, dispatcher):
        self.dispatcher = dispatcher

    @aiozmq.rpc.method
    async def run_command(self, command):
        result = await self.dispatcher.run_command(command)
        return result
