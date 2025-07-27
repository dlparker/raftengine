

class FakeRPCPipe:

    def __init__(self, dispatcher):
        self.dispatcher = dispatcher

    async def run_command(self, command):
        return await self.dispatcher.run_command(command)
