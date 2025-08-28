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

    direct_commands = ['stop', 'status', 'getpid', 'get_leader', 'take_power']
    
    def __init__(self, raft_server, logger):
        self.raft_server = raft_server
        self.logger = logger

    async def direct_server_command(self, in_command: str):
        # Some commands to help manage server processes
        command = in_command.split(' ')[0]
        if command not in self.direct_commands:
            return f"Error, command {command} unknown, should be one of {self.direct_commands}"
        if command == "getpid":
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
        elif command == "status":
            res = await self.get_status()
            return res
        elif command == "get_leader":
            leader = await self.raft_server.deck.get_leader_uri()
            return leader
        return f"unrecognized command '{command}'"

    async def get_status(self):
        res = dict(pid=os.getpid(),
                   datetime=datetime.datetime.now().isoformat(),
                   working_dir=str(self.raft_server.working_dir),
                   raft_log_file=str(self.raft_server.raft_log_file),
                   timers_running=self.raft_server.timers_running,
                   leader_uri=await self.raft_server.deck.get_leader_uri(),
                   uri=self.raft_server.deck.get_my_uri(),
                   is_leader=self.raft_server.deck.is_leader(),
                   cluster_name=self.raft_server.cluster_name,
                   first_log_index=await self.raft_server.deck.log.get_first_index(),
                   last_log_index=await self.raft_server.deck.log.get_last_index(),
                   last_log_term=await self.raft_server.deck.log.get_last_term(),
                   log_commit_index=await self.raft_server.deck.log.get_commit_index(),
                   log_apply_index=await self.raft_server.deck.log.get_applied_index(),
                   term=await self.raft_server.deck.log.get_term())
        return res
