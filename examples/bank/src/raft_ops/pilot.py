import logging
from pathlib import Path
import traceback
from operator import methodcaller
from typing import Dict, Any
from raftengine.api.pilot_api import PilotAPI
from raftengine.api.log_api import LogAPI
from raftengine.api.snapshot_api import SnapShot, SnapShotToolAPI
from raftengine.deck.deck import Deck
from raftengine.messages.message_codec import MessageCodec

logger = logging.getLogger("Pilot")

class Pilot(PilotAPI):

    def __init__(self, log, client_maker, dispatcher):
        self.dispatcher = dispatcher
        self.client_maker = client_maker
        self.log = log
        self.other_node_clients = {}
        self.msg_index = 0
        self.replies = {}
        self.deck = None
        self.shutdown_flag = False
        
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
            result = await self.dispatcher.run_command(command)
            return result, None  
        except Exception as e:
            error_data = traceback.format_exc()
            return None, error_data  

    # PilotAPI
    async def send_message(self, target_uri: str, message:str, serial_number: int) -> None:
        # Don't try to send messages if we're shutting down
        if self.shutdown_flag:
            return None
            
        try:
            msg = MessageCodec.decode_message(message)
            logger.info(f"pilot told to send message {msg.code} to {msg.receiver}")
            
            cli = await self.ensure_node_connection(target_uri)
            msgstr = message.decode()
            result = await cli.raft_message(msgstr)
        except Exception as e:
            # Only log errors if we're not shutting down
            if not self.shutdown_flag:
                logger.error(f"Failed to send message to {target_uri}: {e}")
                logger.error(traceback.format_exc())
            # target server not reachable due to any error is a condition to tolerate
            return None

    # PilotAPI
    async def send_response(self, target_uri: str, orig_message:str, reply:str, orig_serial_number: int) -> None:
        # Don't try to send responses if we're shutting down
        if self.shutdown_flag:
            return None
            
        try:
            msg = MessageCodec.decode_message(reply)
            logger.info(f"pilot told to reply {msg.code} to {msg.receiver}")
            
            cli = await self.ensure_node_connection(target_uri)
            result = await cli.raft_message(reply.decode())
        except Exception as e:
            # Only log errors if we're not shutting down
            if not self.shutdown_flag:
                logger.error(f"Failed to send response to {target_uri}: {e}")
                logger.error(traceback.format_exc())
            # target server not reachable due to any error is a condition to tolerate
            return None
        
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
        logger.info("Pilot received stop command, setting shutdown flag and closing connections")
        self.shutdown_flag = True
        
        # Close all client connections
        for uri, client in list(self.other_node_clients.items()):
            try:
                await client.close()
            except Exception as e:
                logger.debug(f"Error closing connection to {uri}: {e}")
        
        self.other_node_clients.clear()
        
    async def ensure_node_connection(self, target_uri):
        if target_uri not in self.other_node_clients:
            rpc_client = await self.client_maker(target_uri)
            self.other_node_clients[target_uri] = rpc_client
        return self.other_node_clients[target_uri]


