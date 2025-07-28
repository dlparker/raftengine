import json
import os
import time
import asyncio
import traceback
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from logging.config import dictConfig
from collections import defaultdict
from raftengine.deck.deck import Deck
from raftengine.api.types import CommandResult
from raftengine.deck.log_control import LogController

from base.counters import Counters
from split_base.dispatcher import Dispatcher
from rpc.rpc_server import RPCServer
from rpc.rpc_client import RPCClient

log_controller = LogController.get_controller()
logger = log_controller.add_logger("raft.RaftServer",
                                   "The application's implemention of the Raftengine PilotAPI and other server functions")


from raft.pilot import Pilot
from raft.sqlite_log import SqliteLog


class RaftServer:

    def __init__(self, initial_cluster_config, local_config):
        self.initial_config = initial_cluster_config
        self.local_config = local_config
        self.uri = local_config.uri
        self.working_dir = Path(local_config.working_dir)
        self.raft_log_file = Path(self.working_dir, "raftlog.db")
        self.log = SqliteLog(self.raft_log_file)
        self.counters = Counters(self.working_dir)
        self.dispatcher = Dispatcher(self.counters)
        self.pilot = Pilot(self.log, self.dispatcher)
        self.deck = Deck(self.initial_config, self.local_config, self.pilot)
        self.rpc_server = RPCServer(self)
        self.timers_running = False
        self.stopped = False

    # local only method
    async def start(self):
        if not self.timers_running:
            logger.info("calling deck start")
            await self.log.start()
            await self.deck.start()
            port = self.uri.split(':')[-1]
            await self.rpc_server.start(port)
            self.stopped = False
            self.timers_running = True

    # local method reachable through local_command RPC
    async def stop(self):
        self.profiler.disable()
        self.profiler.dump_stats(Path(self.working_dir, 'profile.prof'))
        async def stopper(delay):
            try:
                await asyncio.sleep(delay)
                await self.stop_raft()
                await self.rpc_server.stop()
                logger.warning("Raft server operations stopped on stop_server local command RPC")
            except:
                traceback.print_exc()
        delay = 0.05
        asyncio.create_task(stopper(delay))
        return delay
    
        
    # RPC method
    async def issue_command(self, command: str) -> CommandResult:
        reply = None
        try:
            result = await self.deck.run_command(command, 1.0)
            # this is a CommandResult, convert it to a dict and serialize
            reply = json.dumps(result, default=lambda o:o.__dict__)
            print(reply)
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
    async def direct_server_command(self, command: str):
        # Some trivial commands, might even want to
        # have them in real server. Pings can help
        # validate that a server is alive when it
        # seems to have trouble processing actual
        # work, and getpid can help with process monitoring
        # and forced shutdown. 
        if command == "ping":
            return "pong"
        elif command == "getpid":
            return os.getpid()
        elif command == "shutdown":
            async def shutter():
                await asyncio.sleep(0.001)
                logger.warning("Got signal to shutdown, stopping RaftServer")
                try:
                    await self.stop()
                except:
                    traceback.print_exc()
                await asyncio.sleep(0.01)
                logger.warning("Got signal to shutdown, exiting")
                raise SystemExit(0)
            asyncio.create_task(shutter())
            print(f'server {self.uri} shutting down')
            return "shutting down"
        elif command == "take_power":
            # This can be dangerous if you don't know what you
            # are doing. Issuing it will cause an election with
            # this server winning, maybe, depending on the election
            # rules. Doing this for no reason is dumb as it just
            # makes the cluster less stable. However, it
            # can be useful during development if you want to
            # start with timers set to some huge value so you
            # can probe and debug the server without Raft timeouts
            # happening, in which case you'll need to call this
            # to get the inital election done.
            await self.deck.start_campaign()
            return "started campaign"
        elif command == "stop_raft":
            # If you want to do some server administration with 
            # All raft activity disabled, here's how to do it
            if self.pilot:
                await self.pilot.stop_commanded()
            if self.deck:
                await self.deck.stop()
                await self.log.stop()
                logger.warning("Raft server operations stopped on command")
            self.stopped = True
            self.timers_running = False
            return "stopped raft"
        elif command == "get_status":
            res = dict(pid=os.getpid(),
                       working_dir=str(self.working_dir),
                       raft_log_file=str(self.raft_log_file),
                       timers_running=self.timers_running,
                       leader_uri=await self.deck.get_leader_uri(),
                       uri=self.deck.get_my_uri(),
                       is_leader=self.deck.is_leader(),
                       last_log_index=await self.deck.log.get_last_index(),
                       last_log_term=await self.deck.log.get_last_term(),
                       term=await self.deck.log.get_term())
            return res
        elif command == "get_logging_dict":
            return LogController.get_controller().to_dict_config()
        elif command.startswith == "set_logging_level":
            tmp = commands.split(' ')
            if len(tmp) < 2:
                return "set_logging_level needs at least one argument"
            if len(tmp) > 2:
                level = tmp[2]
                name = tmp[1]
            else:
                level = tmp[1]
                name = ""
            lc = LogController.get_controller()
            lc.set_logger_level(logger, evel)
            res = f"logging for name '{name}' set to {level}"
            return res
        return f"unrecognized command '{command}'"
        

    

