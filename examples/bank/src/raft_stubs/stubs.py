import json
from pathlib import Path
from raftengine.api.types import CommandResult
from base.operations import Teller
from base.proxy import TellerProxyAPI
from base.dispatcher import Dispatcher
from base.rpc_api import RPCAPI
from raft_ops.local_ops import LocalDispatcher

class DeckStub:

    def __init__(self, clear=False):
        db_path = Path("/tmp/bank.db")
        if clear and db_path.exists():
            db_path.unlink()
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
        self.rpc_server_stopper = None
        self.local_dispatcher = Dispatcher(self)

    # RPC method
    async def run_command(self, command):
        raw_result = await self.deck.run_command(command)
        return raw_result

    # RPC method
    async def raft_message(self, message):
        return await self.deck.on_message(message)

    # RPC method
    async def local_command(self, command):
        return await self.local_dispatcher.local_command(command)

    # local method reachable through local_command RPC
    async def start(self):
        logger.info("calling deck start")
        await self.deck.start()
        self.stopped = False
    
    # local method reachable through local_command RPC
    async def stop(self, stop_rpc_server=True):
        await self.deck.stop()
        self.stopped = True
        if stop_rpc_server and self.rpc_server_stopper:
            await self.rpc_server_stopper()

    # local method reachable through local_command RPC
    @staticmethod
    async def get_pid():
        return os.getpid()

    # local only method
    def set_rpc_server_stopper(self, stopper):
        self.rpc_server_stopper = stopper

        
class RaftClient(RPCAPI):
    """
    """

    def __init__(self, rpc_client, client_maker=None):
        self.current_leader = rpc_client.get_uri()
        self.rpc_client = rpc_client
        
    def get_uri(self):
        return self.current_leader
    

    async def raft_message(self, message:str) -> None:
        return await self.rpc_client.raft_message(message)
        
    async def run_command(self, command:str) -> CommandResult:
        result = await self.rpc_client.run_command(command)
        if result.result:
            return result.result
        if result.error:
            raise Exception(f'got error from server {result.error}')
        if result.timeout_expired:
            raise Exception(f'got timeout at server, cluster not available')
        if result.redirect:
            raise Exception(f'got redirect from stub????')
        if not result.retry:
            raise Exception(f"Command result does not make sense {result.__dict__}")
        start_time = time.time()
        while result.retry and time.time() - start_time < 1.0:
            await asyncio.sleep(0.0001)
            result = self.rpc_client.run_command(command)
        if result.retry:
            raise Exception('could not process message at server, cluster not available')
        
    async def local_command(self, command:str) -> str:
        result = await self.rpc_client.local_command(command)

    

    
