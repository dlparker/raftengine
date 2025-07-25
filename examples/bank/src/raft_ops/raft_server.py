import os
import time
import asyncio
import traceback
import logging
import cProfile
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import timedelta, date
from decimal import Decimal
from logging.config import dictConfig
from collections import defaultdict
import jsonpickle
from raftengine.deck.deck import Deck
from raftengine.api.types import CommandResult
from raftengine.deck.log_control import LogController
from base.operations import Teller
from base.datatypes import Customer, Account, AccountType, CommandType
from base.dispatcher import Dispatcher
from raft_ops.pilot import Pilot
from raft_ops.local_ops import LocalDispatcher
from raft_ops.sqlite_log import SqliteLog

log_controller = LogController.get_controller()
logger = log_controller.add_logger("raft_ops.RaftServer",
                                   "The application's implemention of the Raftengine PilotAPI")

class RaftServer:

    def __init__(self, initial_cluster_config, local_config, rpc_helper):
        self.initial_config = initial_cluster_config
        self.local_config = local_config
        self.working_dir = Path(local_config.working_dir)
        self.app_db_file = Path(self.working_dir, "bank.db")
        self.teller = Teller(self.app_db_file)
        self.raft_log_file = Path(self.working_dir, "raftlog.db")
        self.log = SqliteLog(self.raft_log_file)
        self.log.start()
        self.timers_running = False
        self.stopped = False
        self.rpc_server_stopper = None
        self.profiler = cProfile.Profile()
        self.profiler.enable()
        
        tmp = local_config.uri.split('/')
        transport = tmp[0].split(':')[0]
        host, port = tmp[-1].split(':')
        self.rpc_helper = rpc_helper(port)
        self.client_maker = self.rpc_helper.rpc_client_maker
        self.dispatcher = Dispatcher(self.teller)
        self.local_dispatcher = LocalDispatcher(self)
        self.pilot = Pilot(self.log, self.client_maker, self.dispatcher)
        self.deck = Deck(self.initial_config, self.local_config, self.pilot)
        self.pilot.set_deck(self.deck)

    # RPC method
    async def run_command(self, command: str) -> CommandResult:
        reply = None
        try:
            reply = await self.deck.run_command(command, 1.0)
        except Exception as e:
            logger.error(traceback.format_exc())
            # target server not reachable due to any error is a condition to tolerate
        return reply

    # RPC method
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
        
    # RPC method executed locally, not via Raft replication
    async def local_command(self, command: str):
        return await self.local_dispatcher.local_command(command)

    # local only method
    async def start(self):
        if not self.timers_running:
            logger.info("calling deck start")
            await self.deck.start()
            self.stopped = False
            self.timers_running = True
            
    
    # local method reachable through local_command RPC
    async def start_raft(self):
        return await self.start()

    # local method reachable through local_command RPC
    async def start_campaign(self):
        return await self.deck.start_campaign()

    async def stop_raft(self):
        if self.pilot:
            await self.pilot.stop_commanded()
        if self.deck:
            await self.deck.stop()
            logger.warning("Raft server operations stopped on command")
        self.stopped = True
        self.timers_running = False
    
    # local method reachable through local_command RPC
    async def stop_server(self):
        self.profiler.disable()
        self.profiler.dump_stats(Path(self.working_dir, 'profile.prof'))
        async def stopper(delay):
            try:
                await asyncio.sleep(delay)
                await self.stop_raft()
                await self.rpc_server_stopper()
                logger.warning("Raft server operations stopped on stop_server local command RPC")
            except:
                traceback.print_exc()
        delay = 0.05
        asyncio.create_task(stopper(delay))
        return delay
        
    # local method reachable through local_command RPC
    @staticmethod
    async def get_pid():
        return os.getpid()
        
    # local method reachable through local_command RPC
    async def get_status(self):
        res = dict(pid=os.getpid(),
                   working_dir=str(self.working_dir),
                   raft_log_file=str(self.raft_log_file),
                   teller_file=str(self.app_db_file),
                   timers_running=self.timers_running,
                   leader_uri=await self.deck.get_leader_uri(),
                   uri=self.deck.get_my_uri(),
                   is_leader=self.deck.is_leader(),
                   last_log_index=await self.deck.log.get_last_index(),
                   last_log_term=await self.deck.log.get_last_term(),
                   term=await self.deck.log.get_term(),
                   customer_count=await self.teller.get_customer_count(),
                   account_count=await self.teller.get_account_count())
        return res

    # local method reachable through local_command RPC
    async def get_logging_dict(self) -> dict:
        return LogController.get_controller().to_dict_config()

    # local method reachable through local_command RPC
    async def set_logging_level(self, level:str, loggers:Optional[list[str]]) -> dict:
        lc = LogController.get_controller()
        if loggers is None or len(loggers) == 0:
            lc.set_default_level(level)
            return
        res = {}
        for logger in loggers:
            try:
                lc.set_logger_level(logger, level)
                res[logger] = "set to " + level
            except ValueError:
                res[logger] = "logger not registered with LogControl"
        return res
    
    # local only method
    def set_rpc_server_stopper(self, stopper):
        self.rpc_server_stopper = stopper

