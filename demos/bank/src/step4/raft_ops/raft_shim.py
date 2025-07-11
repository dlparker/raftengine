import logging
logger = logging.getLogger(__name__)

class RaftShim:

    def __init__(self, dispatcher):
        self.dispatcher = dispatcher
        
    async def raft_message(self, command:str):
        logger.debug("Calling dispatcher.run_command")
        return await self.dispatcher.run_command(command)
