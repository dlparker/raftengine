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
from raftengine.deck.deck import Deck
from raftengine.api.types import CommandResult
from raftengine.deck.log_control import LogController
from raftengine_logs.sqlite_log.sqlite_log import SqliteLog
from raftengine_logs.memory_log.memory_log import MemoryLog
from raftengine_logs.lmdb_log.lmdb_log import LmdbLog
from raftengine_logs.hybrid_log.hybrid_log import HybridLog


#from base.counters import Counters
from raft.raft_counters import RaftCounters
from raft.pilot import Pilot
from split_base.dispatcher import Dispatcher

log_controller = LogController.get_controller()
logger = log_controller.add_logger("raft.RaftServer",
                                   "The application's implemention of the Raftengine PilotAPI and other server functions")



class RaftServer:

    direct_commands = ['ping', 'stop', 'status', 'getpid', 'dump_status', 'start_raft',
                       'take_power', 'get_logging_dict', 'set_logging_level', 'take_snapshot', 'log_stats']
    def __init__(self, initial_cluster_config, local_config, rpc_server_class, rpc_client_class, 
                 start_paused=False, log_type='memory'):
        self.initial_config = initial_cluster_config
        self.local_config = local_config
        self.start_paused = start_paused
        self.rpc_server_class = rpc_server_class
        self.rpc_client_class = rpc_client_class
        self.uri = local_config.uri
        self.working_dir = Path(local_config.working_dir)
        self.raft_log_file = Path(self.working_dir, "raftlog.db")
        self.lmdb_log_file = Path(self.working_dir, "raftlog.lmdb")
        self.hybrid_dir = Path(self.working_dir, "hybrid_raftlog")
        
        # Initialize log based on type
        if log_type == 'sqlite':
            self.log = SqliteLog(self.raft_log_file)
        elif log_type == 'lmdb':
            self.log = LmdbLog(self.lmdb_log_file)
        elif log_type == 'hybrid':
            if not self.hybrid_dir.exists():
                self.hybrid_dir.mkdir(parents=True)
            # These values are chosen to make the hybrid log actually have to
            # do the archiving operations during performance testing, as those
            # runs typically use loop counts in the tens of thousands. 
            self.log = HybridLog(dirpath=self.hybrid_dir, hold_count=5000,
                                 push_trigger=100, push_snap_size=200,
                                 copy_block_size=100)
        elif log_type == 'memory':
            self.log = MemoryLog()
        else:
            raise ValueError(f"Unknown log type: {log_type}. Valid types: memory, sqlite, lmdb, hybrid")
        self.counters = RaftCounters(self.working_dir)
        self.dispatcher = Dispatcher(self.counters)
        self.pilot = Pilot(self.log, self.dispatcher, self.rpc_client_class)
        self.deck = Deck(self.initial_config, self.local_config, self.pilot)
        self.rpc_server = self.rpc_server_class(self)
        self.timers_running = False
        self.stopped = False
        self.stopping = False
        self.stop_reply_sent = False
        with open(Path(self.working_dir, 'server.pid'), 'w') as f:
            f.write(f"{os.getpid()}")
        print(f"Raft server on {self.uri} created\n")
        print(f"   working_dir={self.working_dir}")
        print(f"   nodes = {self.initial_config.node_uris}")
            

    # local only method
    async def start(self):
        self.start_paused = self.start_paused
        if not self.timers_running:
            logger.info("calling deck start")
            await self.log.start()
            term = await self.log.get_term()
            if not self.start_paused:
                await self.deck.start()
            print(f"Raft server on {self.uri} started\n")
            config = await self.deck.cluster_ops.get_cluster_config()
            print(f"   config = {json.dumps(config, indent=4, default=lambda o:o.__dict__)}")
            port = self.uri.split(':')[-1]
            self.stopped = False
            self.timers_running = True
            await self.rpc_server.start(port)
                
    # local method reachable through local_command RPC
    async def start_raft(self):
        if not self.deck.started:
            await self.deck.start()
        
    # local method reachable through local_command RPC
    async def stop(self):
        async def stopper(delay=2.0):
            await self.rpc_server.stop()
            await asyncio.sleep(delay)
            try:
                await self.stop_raft()
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
        # Some trivial commands, might even want to
        # have them in real server. Pings can help
        # validate that a server is alive when it
        # seems to have trouble processing actual
        # work, and getpid can help with process monitoring
        # and forced shutdown.
        command = in_command.split(' ')[0]
        if command not in self.direct_commands:
            return f"Error, command {command} unknown, should be one of {self.direct_commands}"
        if command == "ping":
            return "pong"
        elif command == "getpid":
            return os.getpid()
        elif command == "stop":
            async def shutter():
                await asyncio.sleep(0.001)
                logger.warning("Got signal to shutdown, stopping RaftServer")
                try:
                    # Wait for the stopper task to complete instead of just creating it
                    await self.stop()
                except Exception as e:
                    traceback.print_exc()
                await asyncio.sleep(0.1)  # Additional safety margin
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
            await self.start_raft()
            await self.deck.start_campaign()
            return "started campaign"
        elif command == "start_raft":
            # you can start the server in a paused state, meaning
            # that it won't do any raft operations until you run 
            # this command or the 'take_power' command
            await self.start_raft()
            return "started raft ops"
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
        elif command == "status" or command == "dump_status":
            res = dict(pid=os.getpid(),
                       datetime=datetime.datetime.now().isoformat(),
                       working_dir=str(self.working_dir),
                       raft_log_file=str(self.raft_log_file),
                       timers_running=self.timers_running,
                       leader_uri=await self.deck.get_leader_uri(),
                       uri=self.deck.get_my_uri(),
                       is_leader=self.deck.is_leader(),
                       first_log_index=await self.deck.log.get_first_index(),
                       last_log_index=await self.deck.log.get_last_index(),
                       last_log_term=await self.deck.log.get_last_term(),
                       log_commit_index=await self.deck.log.get_commit_index(),
                       log_apply_index=await self.deck.log.get_applied_index(),
                       term=await self.deck.log.get_term())
            if command == "dump_status":
                # write it to standard out
                print("\n\n-------------- STATUS DUMP BEGINS --------------\n")
                for key in res: # get them in the order written
                    print(f"{key:20s}: {res[key]}")
                print("\n\n-------------- STATUS DUMP ENDS --------------\n", flush=True)
            return res
        elif command == "get_logging_dict":
            return LogController.get_controller().to_dict_config()
        elif command == "set_logging_level":
            tmp = in_command.split(' ')
            if len(tmp) < 2:
                return "set_logging_level needs at least one argument"
            lc = LogController.get_controller()
            if len(tmp) > 2:
                level = tmp[2]
                name = tmp[1]
                lc.set_logger_level(logger, level)
            else:
                level = tmp[1]
                name = ""
                lc.set_default_level(level)
            res = f"logging for name '{name}' set to {level}"
            return res
        elif command == "take_snapshot":
            snap = await self.deck.take_snapshot()
            return dict(snap.__dict__)
        elif command == "log_stats":
            stats = await self.log.get_stats()
            return dict(stats.__dict__)
        return f"unrecognized command '{command}'"
        

    

