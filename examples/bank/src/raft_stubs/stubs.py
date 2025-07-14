from base.operations import Teller
from base.proxy import TellerProxyAPI
from base.dispatcher import Dispatcher


class DeckStub:

    def __init__(self):
        self.teller = Teller("/tmp/bank.db")
        self.dispatcher = Dispatcher(self.teller)

    async def run_command(self, command):
        return await self.dispatcher.run_command(command)

    async def on_rpc_message(self, message):
        # for this stage just be an echo server
        return message

class RaftServerStub:

    def __init__(self, deck):
        self.deck = deck

    async def run_command(self, command):
        return await self.deck.run_command(command)

    async def raft_message(self, message):
        return await self.deck.on_rpc_message(message)
        

    

    
