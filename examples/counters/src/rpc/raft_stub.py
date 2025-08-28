import os
import asyncio
import traceback

class RaftServerStub():
    """
    This is a stub implementation of what should be the core of a server
    process. It gathers together and initializes the components need to
    run a Raftengine enabled server.
    """
    def __init__(self, rpc_server_class, dispatcher, port):
        self.dispatcher = dispatcher
        self.port = port
        self.rpc_server = rpc_server_class(self)

    async def start(self, shutdown_callback=None):
        self.shutdown_callback = shutdown_callback
        await self.rpc_server.start(self.port)
    
    async def stop(self):
        await self.rpc_server.stop()
        if self.shutdown_callback:
            asyncio.create_task(self.shutdown_callback(self))
    
    async def issue_command(self, command, timeout):
        result = await self.dispatcher.route_command(command)
        return result

    async def raft_message(self, message):
        # just return the message to allow checking for basic
        # RPC functionality
        return message

    async def direct_server_command(self, command):
        # Some trivial commands, might even want to
        # have them in real server. Pings can help
        # validate that a server is alive when it
        # seems to have trouble processing actual
        # work, and getpid can help with process monitoring
        # and forced shutdown. 
        if command == "ping":
            return "pong"
        if command == "getpid":
            return os.getpid()
        if command == "shutdown":
            async def stopper(delay):
                await asyncio.sleep(delay)
                try:
                    await self.stop()
                except asyncio.CancelledError:
                    pass
                except:
                    traceback.print_exc()
            delay = 0.1
            asyncio.create_task(stopper(delay))
            return "shutting down"
        return command


