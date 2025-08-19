import json
import os
import time
import asyncio
import traceback
import logging
import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import asdict
from raftengine.api.types import ClusterConfig, NodeRec, ClusterSettings
from raftengine.api.log_api import LogStats
from raftengine.api.snapshot_api import SnapShot
from raftengine.deck.log_control import LogController
from raft.raft_client import RaftClient

class DirectCommander:

    direct_commands = ['ping', 'stop', 'status', 'getpid', 'dump_status', 'start_raft', 'get_config',
                       'take_power', 'get_logging_dict', 'set_logging_level', 'take_snapshot', 'log_stats']
    
    def __init__(self, raft_server, logger):
        self.raft_server = raft_server
        self.logger = logger

    async def direct_server_command(self, in_command: str):
        # Some commands to help manage server processes
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
                self.logger.warning("Got signal to shutdown, stopping RaftServer")
                try:
                    # Wait for the stopper task to complete instead of just creating it
                    await self.raft_server.stop()
                except Exception as e:
                    traceback.print_exc()
                await asyncio.sleep(0.1)  # Additional safety margin
                self.logger.warning("Got signal to shutdown, exiting")
                raise SystemExit(0)
            asyncio.create_task(shutter())
            print(f'server {self.raft_server.uri} shutting down', flush=True)
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
            await self.raft_server.deck.start_campaign()
            return "started campaign"
        elif command == "stop_raft":
            # If you want to do some server administration with 
            # All raft activity disabled, here's how to do it
            if self.raft_server.pilot:
                await self.raft_server.pilot.stop_commanded()
            if self.raft_server.deck:
                await self.raft_server.deck.stop()
                await self.raft_server.log.stop()
                self.logger.warning("Raft server operations stopped on command")
            self.raft_server.stopped = True
            self.raft_server.timers_running = False
            return "stopped raft"
        elif command == "status" or command == "dump_status":
            res = dict(pid=os.getpid(),
                       datetime=datetime.datetime.now().isoformat(),
                       working_dir=str(self.raft_server.working_dir),
                       raft_log_file=str(self.raft_server.raft_log_file),
                       timers_running=self.raft_server.timers_running,
                       leader_uri=await self.raft_server.deck.get_leader_uri(),
                       uri=self.raft_server.deck.get_my_uri(),
                       is_leader=self.raft_server.deck.is_leader(),
                       first_log_index=await self.raft_server.deck.log.get_first_index(),
                       last_log_index=await self.raft_server.deck.log.get_last_index(),
                       last_log_term=await self.raft_server.deck.log.get_last_term(),
                       log_commit_index=await self.raft_server.deck.log.get_commit_index(),
                       log_apply_index=await self.raft_server.deck.log.get_applied_index(),
                       term=await self.raft_server.deck.log.get_term())
            if command == "dump_status":
                # write it to standard out
                print("\n\n-------------- STATUS DUMP BEGINS --------------\n")
                for key in res: # get them in the order written
                    print(f"{key:20s}: {res[key]}")
                print("\n\n-------------- STATUS DUMP ENDS --------------\n", flush=True)
            return res
        elif command == "get_logging_dict":
            return LogController.get_controller().to_dict_config()
        elif command == "get_config":
            return asdict(await self.raft_server.deck.get_cluster_config())
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
            snap = await self.raft_server.deck.take_snapshot()
            return dict(snap.__dict__)
        elif command == "log_stats":
            stats = await self.raft_server.log.get_stats()
            return dict(stats.__dict__)
        return f"unrecognized command '{command}'"
        

    
class DirectCommandClient:

    def __init__(self, uri, raft_client=None):
        self.uri = uri
        self.raft_client = raft_client
        if raft_client is None:
            self.raft_client = RaftClient(self.uri, timeout=1.0)

    async def close(self):
        if self.raft_client:
            await self.raft_client.close()
            
    async def ping(self):
        return await self.raft_client.direct_server_command('ping')

    async def getpid(self):
        return int(await self.raft_client.direct_server_command('getpid'))
    
    async def stop(self):
        return await self.raft_client.direct_server_command('stop')

    async def take_power(self):
        return await self.raft_client.direct_server_command('take_power')

    async def stop_raft(self):
        return await self.raft_client.direct_server_command('stop_raft')
    
    async def get_status(self):
        return await self.raft_client.direct_server_command('status')
    
    async def dump_status(self):
        return await self.raft_client.direct_server_command('dump_status')
    
    async def get_logging_dict(self):
        return await self.raft_client.direct_server_command('get_logging_dict')
    
    async def get_cluster_config(self):
        config_data =  await self.raft_client.direct_server_command('get_config')
        settings = ClusterSettings(**config_data['settings'])
        nodes = {}
        for n_uri,nr in config_data['nodes'].items():
            nodes[n_uri] = (NodeRec(**nr))
        config = ClusterConfig(nodes, settings=settings)
        return config
    
    async def set_logging_level(self, logger_name=None, level="error"):
        cmd  = "set_logging_level"
        if logger_name is not None:
            cmd += f" {logger_name}"
        cmd += f" {level}"
        return await self.raft_client.direct_server_command(cmd)
    
    async def take_snapshot(self):
        res =  await self.raft_client.direct_server_command('take_snapshot')
        return SnapShot(**res)

    async def log_stats(self):
        res = await self.raft_client.direct_server_command('log_stats')
        return LogStats(**res)
