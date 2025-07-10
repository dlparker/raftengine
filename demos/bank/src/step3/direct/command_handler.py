
class CommandHandler:

    def __init__(self, dispatcher):
        self.dispatcher = dispatcher
        
    async def run_command(self, command:str):
        return await self.dispatcher.do_command(command)
