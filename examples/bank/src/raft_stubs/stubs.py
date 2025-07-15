import json
from pathlib import Path
from base.operations import Teller
from base.proxy import TellerProxyAPI
from base.dispatcher import Dispatcher
from raftengine.api.deck_api import CommandResult

class DeckStub:

    def __init__(self, clear=False):
        db_path = Path("/tmp/bank.db")
        self.teller = Teller(db_path)
        self.dispatcher = Dispatcher(self.teller)

    async def run_command(self, command):
        result = await self.dispatcher.run_command(command)
        return CommandResult(command=command, result=result)

    async def on_message(self, message):
        # for this stage just be an echo server
        return message

class RaftServerStub:

    def __init__(self, deck):
        self.deck = deck

    async def run_command(self, command):
        raw_result = await self.deck.run_command(command)
        return raw_result

    async def raft_message(self, message):
        return await self.deck.on_message(message)


class CommandClient:
    
    def __init__(self, rpc_client):
        self.rpc_client = rpc_client

    async def run_command(self, command):
        command_result = await self.rpc_client.run_command(command)
        if command_result.error:
            raise Exception(command_result.error)
        if command_result.timeout_expired:
            raise Exception("timeout expired")
        if command_result.redirect:
            raise Exception(f"Redirected to {command_result.redirect}")
        if command_result.retry:
            raise Exception(f"Retry needed")
        return command_result.result

        
        

    

    
