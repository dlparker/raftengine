import logging
from pathlib import Path
import traceback
from operator import methodcaller
from typing import Dict, Any
from raftengine.api.pilot_api import PilotAPI
from raftengine.api.log_api import LogAPI
from raftengine.api.snapshot_api import SnapShot, SnapShotToolAPI
from raftengine.deck.deck import Deck
from base.json_helpers import bank_json_dumps, bank_json_loads

logger = logging.getLogger("Pilot")

class Pilot(PilotAPI):

    def __init__(self, log, setup_helper, dispatcher, reply_callback):
        self.dispatcher = dispatcher
        self.setup_helper = setup_helper
        self.reply_callback = reply_callback
        self.log = log
        self.other_node_clients = {}
        self.msg_index = 0
        self.replies = {}
        self.deck = None
        
    def set_deck(self, deck):
        # this is not in the __init__ because the Deck __init__ needs a reference
        # to this class, so that has to be done first
        self.deck = deck
            
    # PilotAPI
    def get_log(self) -> LogAPI: 
        return self.log
    
    # PilotAPI
    async def process_command(self, command: str, serial: int) -> tuple:
        # The raftengine expects process_command to return a tuple: (result, error)
        # where error is None on success, or error message string on failure
        try:
            logger.debug(f"Pilot processing command: {command}")
            logger.debug(f"Command serial: {serial}")
            
            result = await self.dispatcher.run_command(command)
            logger.debug(f"Pilot got result from dispatcher: {type(result)}")
            logger.debug(f"Result preview: {str(result)[:200]}..." if len(str(result)) > 200 else f"Result: {result}")
            
            return result, None  # Success: return result and no error
            
        except Exception as e:
            error_data = traceback.format_exc()
            logger.error(f"Pilot.process_command failed:")
            logger.error(f"Command: {command}")
            logger.error(f"Serial: {serial}")
            logger.error(f"Exception type: {type(e).__name__}")
            logger.error(f"Exception message: {str(e)}")
            logger.error(f"Full traceback: {error_data}")
            return None, error_data  # Failure: return None and error message

    # PilotAPI
    async def send_message(self, target_uri: str, message:str, serial_number: int) -> None:
        logger.debug(f"message for target {target_uri}")
        cli = await self.ensure_node_connection(target_uri)
        try:
            logger.debug(f"sending message for target {target_uri}")
            result = await cli.raft_message(message)
        except Exception as e:
            logger.debug(traceback.format_exc())
            # target server not there is a condition to tolerate
            return None

        try:
            logger.debug(f"handling raft_message result from {target_uri}")
            await self.deck.on_message(result)
        except Exception as e:
            logger.debug(traceback.format_exc())
            raise SystemExit()

    # PilotAPI
    async def send_response(self, target_uri: str, orig_message:str, reply:str, orig_serial_number: int) -> None:
        logger.debug(f"response for target {target_uri}")
        await self.reply_callback(target_uri, orig_message, reply)
        
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
            tmp = target_uri.split('/')
            host, port = tmp[-1].split(':')
            rpc_client = await self.setup_helper.get_rpc_client(host, port)
            self.other_node_clients[target_uri] = rpc_client
        return self.other_node_clients[target_uri]


