import logging
import time
import asyncio
import traceback
from pathlib import Path
from typing import Dict, Any
from datetime import timedelta, date
from decimal import Decimal
from collections import defaultdict
from raftengine.deck.deck import Deck
from raftengine.api.deck_api import CommandResult
from base.operations import Teller
from base.datatypes import Customer, Account, AccountType, CommandType
from base.dispatcher import Dispatcher
from raft_ops.sqlite_log import SqliteLog
from raft_ops.pilot import Pilot

logger = logging.getLogger("RaftServer")

class RaftServer:

    def __init__(self, initial_cluster_config, local_config, client_maker):
        self.initial_config = initial_cluster_config
        self.local_config = local_config
        self.working_dir = Path(local_config.working_dir)
        self.client_maker = client_maker
        app_db_file = Path(self.working_dir, "bank.db")
        self.teller = Teller(app_db_file)
        raft_log_file = Path(self.working_dir, "raftlog.db")
        self.log = SqliteLog(raft_log_file)
        self.log.start()
        self.dispatcher = Dispatcher(self.teller)
        self.pilot = Pilot(self.log, self.client_maker, self.dispatcher)
        self.deck = Deck(self.initial_config, self.local_config, self.pilot)
        self.pilot.set_deck(self.deck)
        self.stopped = False
        self.replies = defaultdict(list)

    async def start(self):
        logger.info("calling deck start")
        await self.deck.start()
        self.stopped = False
    
    async def stop(self):
        await self.deck.stop()
        self.stopped = True
        
    async def run_command(self, command: str) -> CommandResult:
        reply = None
        try:
            reply = await self.deck.run_command(command, 1.0)
        except Exception as e:
            logger.error(traceback.format_exc())
            # target server not reachable due to any error is a condition to tolerate
        return reply

    async def raft_message(self, message: str) -> str:
        reply = None
        try:
            msg = self.deck.decode_message(message)
            logger.info(f"Got raft message {msg.code} from {msg.sender}")
            reply = await self.deck.on_message(message)
        except Exception as e:
            logger.error(traceback.format_exc())
            # target server not reachable due to any error is a condition to tolerate
        return reply
        
        
