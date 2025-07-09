from pathlib import Path
import traceback
from operator import methodcaller
from typing import Dict, Any
from raftengine.api.pilot_api import PilotAPI
from raftengine.api.log_api import LogAPI
from raftengine.api.snapshot_api import SnapShot, SnapShotToolAPI
from raftengine.deck.deck import Deck
import sys
top_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(top_dir))
from src.base.json_helpers import bank_json_dumps, bank_json_loads

class DeckHand:

    def __init__(self, server, log, client_maker, initial_config, local_config):
        self.server = server
        self.client_maker = client_maker
        self.log = log
        self.pilot = Pilot(self.server, self.log, self.client_maker)
        self.deck = Deck(initial_config, local_config, self.pilot)
        self.pilot.set_deck(self.deck)

    async def start(self):
        await self.deck.start()

    async def stop(self):
        await self.deck.stop()

    async def raft_message(self, in_message: Dict[str, Any]) -> Dict[str, Any]:
        print('in deckhand.raft_message')
        return await self.deck.on_message(in_message)


class Pilot(PilotAPI):

    def __init__(self, server, log, client_maker):
        self.server = server
        self.client_maker = client_maker
        self.log = log
        self.other_node_clients = {}
        self.msg_index = 0
        self.msg_in_flight = {}
        self.replies = {}
        self.deck = None
        
    def set_deck(self, deck):
        self.deck = deck
            
    # PilotAPI
    def get_log(self) -> LogAPI: 
        return self.log
    
    # PilotAPI
    async def process_command(self, command: str, serial: int) -> str:
        request = bank_json_loads(command)
        try:
            command_name = request.get('command_name')
            argsdict = request.get('args', {})
            callable_method = methodcaller(command_name, **argsdict)
            result = await callable_method(self.server)
            response_data = {"success": True, "result": result}
        except Exception as e:
            response_data = {"success": False, "error": str(e), "error_type": type(e).__name__}
        response = bank_json_dumps(response_data)
        return response

    # PilotAPI
    async def send_message(self, target_uri: str, message:str) -> None:
        print(f"message for target {target_uri}", flush=True)
        cli = await self.ensure_node_connection(target_uri)
        try:
            await cli.raft_message(message)
            print(f"sent message for target {target_uri}", flush=True)
        except Exception as e:
            traceback.print_exc()
            raise SystemExit()

    # PilotAPI
    async def send_response(self, target_uri: str, orig_message:str, reply:str) -> None: 
        for index, msg in self.msg_in_flight.items():
            if msg == orig_message:
                self.replies[index] = msg
                del self.msg_in_flight[index]

    # PilotAPI
    async def begin_snapshot_import(self, snapshot:SnapShot) -> SnapShotToolAPI:
        raise NotImplementedError

    # PilotAPI
    async def begin_snapshot_export(self, snapshot:SnapShot) -> SnapShotToolAPI:
        raise NotImplementedError
    
    # PilotAPI
    async def create_snapshot(self, index:int , term: int) -> SnapShot:
        raise NotImplementedError

    # PilotAPI
    async def stop_commanded(self) -> None:
        pass
        
    async def ensure_node_connection(self, target_uri):
        if target_uri not in self.other_node_clients:
            self.other_node_clients[target_uri] = self.client_maker(target_uri)
        return self.other_node_clients[target_uri]


