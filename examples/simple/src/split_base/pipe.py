

class FakeRPCPipe:

    def __init__(self, dispatcher):
        self.dispatcher = dispatcher

    async def issue_command(self, command, timeout=1.0):
        return await self.dispatcher.route_command(command)
