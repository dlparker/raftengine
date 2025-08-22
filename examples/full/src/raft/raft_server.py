import json
import os
import time
import asyncio
import traceback
import logging
import datetime
from pprint import pprint
from pathlib import Path
from typing import Dict, Any, Optional
from logging.config import dictConfig
from collections import defaultdict
from dataclasses import asdict
from raftengine.deck.deck import Deck
from raftengine.api.types import CommandResult
from raftengine.deck.log_control import LogController
from raftengine_logs.sqlite_log.sqlite_log import SqliteLog

#from base.counters import Counters
from raft.raft_counters import RaftCounters
from raft.pilot import Pilot
from split_base.dispatcher import Dispatcher
from rpc.rpc_client import RPCClient
from rpc.rpc_server import RPCServer
from ops.direct import DirectCommander
log_controller = LogController.get_controller()
logger = log_controller.add_logger("raft.RaftServer","")


class RaftServer:

    def __init__(self, local_config, initial_cluster_config=None, cluster_name=None):
        self.local_config = local_config
        self.initial_config = initial_cluster_config
        self.cluster_name = cluster_name # this is only helpfull in development scnearios,
        self.uri = local_config.uri
        self.working_dir = Path(local_config.working_dir)
        self.raft_log_file = Path(self.working_dir, "raftlog.db")
        self.log = SqliteLog(self.raft_log_file)
        self.counters = RaftCounters(self.working_dir)
        self.dispatcher = Dispatcher(self.counters)
        self.pilot = Pilot(self.log, self.dispatcher)
        self.deck = Deck(self.initial_config, self.local_config, self.pilot)
        self.rpc_server = RPCServer(self)
        self.timers_running = False
        self.stopped = False
        self.stopping = False
        self.stop_reply_sent = False
        self.direct_commander = DirectCommander(self, logger)
        self.direct_commands = DirectCommander.direct_commands
        with open(Path(self.working_dir, 'server.pid'), 'w') as f:
            f.write(f"{os.getpid()}")
        print(f"Raft server on {self.uri} created\n")
        print(f"   working_dir={self.working_dir}")
        print(f"   nodes = {self.initial_config.node_uris}")
            

    # local only method
    async def start(self):
        if not self.timers_running:
            logger.info("calling deck start")
            await self.log.start()
            term = await self.log.get_term()
            await self.deck.start()
            print(f"Raft server on {self.uri} started\n")
            config = await self.deck.cluster_ops.get_cluster_config()
            print(f"   config = {json.dumps(config, indent=4, default=lambda o:o.__dict__)}")
            port = self.uri.split(':')[-1]
            self.stopped = False
            self.timers_running = True
            await self.rpc_server.start(port)
            
    # local only method
    async def start_and_join(self, leader_uri):
        if not self.timers_running:
            logger.info("calling deck start_and_join")
            await self.log.start()
            term = await self.log.get_term()
            port = self.uri.split(':')[-1]
            await self.rpc_server.start(port)
            await self.deck.start_and_join(leader_uri)
            print(f"Raft server on {self.uri} started\n")
            config = await self.deck.cluster_ops.get_cluster_config()
            print(f"   config = {json.dumps(config, indent=4, default=lambda o:o.__dict__)}")
            self.stopped = False
            self.timers_running = True
        
    # local method reachable through local_command RPC
    async def stop(self):
        async def stopper():
            await self.rpc_server.stop()
            await self.deck.stop()
            try:
                pidfile = Path(self.working_dir, 'server.pid')
                if pidfile.exists():
                    pidfile.unlink()
            except Exception as e:
                traceback.print_exc()
        if self.stopping:
            return
        self.stopping = True
        asyncio.create_task(stopper())
        
    # RPC method
    async def issue_command(self, command: str, timeout) -> CommandResult:
        reply = None
        try:
            result = await self.deck.run_command(command, timeout)
            # this is a CommandResult, convert it to a dict for serialization
            logger.debug(result)
            reply = result.__dict__
            logger.debug(reply)
        except Exception as e:
            logger.error(traceback.format_exc())
            # target server not reachable due to any error is a condition to tolerate
            reply = traceback.format_exc()
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
        
    # RPC for commands to be executed locally, not via Raft replication
    async def direct_server_command(self, in_command: str):
        try:
            res = await self.direct_commander.direct_server_command(in_command)
        except:
            res = dict(error=traceback.format_exc())
        return res

    

