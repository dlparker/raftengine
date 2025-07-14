

class FakeRPCPipe:

    def __init__(self, dispatcher):
        self.dispatcher = dispatcher

    async def send_command(self, command):
        return await self.dispatcher.run_command(command)
