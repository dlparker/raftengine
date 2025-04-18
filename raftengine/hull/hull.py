import asyncio
import traceback
import logging
import random
import time
import json

from raftengine.api.types import RoleName, SubstateCode
from raftengine.api.hull_api import CommandResult
from raftengine.messages.base_message import BaseMessage
from raftengine.messages.request_vote import RequestVoteMessage,RequestVoteResponseMessage
from raftengine.messages.append_entries import AppendEntriesMessage, AppendResponseMessage
from raftengine.roles.follower import Follower
from raftengine.roles.candidate import Candidate
from raftengine.roles.leader import Leader
from raftengine.api.pilot_api import PilotAPI
from raftengine.api.hull_api import HullAPI
from raftengine.api.hull_config import ClusterConfig, LocalConfig

class Hull(HullAPI):

    # Part of API
    def __init__(self, cluster_config: ClusterConfig, local_config: LocalConfig, pilot: PilotAPI):
        self.cluster_config = cluster_config
        self.local_config = local_config
        if not isinstance(pilot, PilotAPI):
            raise Exception('Must supply a raftengine.hull.api.PilotAPI implementation')
        self.pilot = pilot
        self.log = pilot.get_log()
        self.role = Follower(self)
        self.logger = logging.getLogger("Hull")
        self.role_async_handle = None
        self.role_run_after_target = None
        self.message_problem_history = []
        self.log_substates = logging.getLogger("Substates")

    # Part of API
    def change_cluster_config(self, cluster_config: ClusterConfig):
        self.cluster_config = cluster_config
        
    # Part of API
    async def start(self):
        await self.role.start()

    # Part of API
    def decode_message(self, in_message):
        mdict = json.loads(in_message)
        mtypes = [AppendEntriesMessage,AppendResponseMessage,
                  RequestVoteMessage,RequestVoteResponseMessage]
        message = None
        for mtype in mtypes:
            if mdict['code'] == mtype.get_code():
                message = mtype.from_dict(mdict)
        if message is None:
            raise Exception('Message is not decodeable as a raft type')
        return message
    
    # Part of API
    async def on_message(self, in_message):
        try:
            message = self.decode_message(in_message)
        except:
            error = traceback.format_exc()
            self.logger.error(error)
            await self.record_message_problem(in_message, error)
            return None
        res = await self.inner_on_message(message)
        return res
        
    async def inner_on_message(self, message):
        res = None
        error = None
        try:
            self.logger.debug("%s Handling message type %s", self.get_my_uri(), message.get_code())
            res = await self.role.on_message(message)
        except Exception as e:
            error = traceback.format_exc()
            self.logger.error(error)
        if error:
            await self.record_message_problem(message, error)
        return res

    # Part of API
    async def run_command(self, command, timeout=1):
        if self.role.role_name == RoleName.leader:
            return await self.role.run_command(command, timeout=timeout)
        elif self.role.role_name == RoleName.follower:
            return CommandResult(command, redirect=self.role.leader_uri)
        elif self.role.role_name == RoleName.candidate:
            return CommandResult(command, retry=1)
    
    # Called by Role
    def get_log(self):
        return self.log

    # Called by Role
    def get_role_name(self):
        return self.role.role_name

    # Called by Role
    def get_my_uri(self):
        return self.local_config.uri
        
    # Called by Role
    def get_processor(self):
        return self.pilot
    
    # Called by Role and in API
    async def get_term(self):
        return await self.log.get_term()

    # Called by Role and in API
    def get_cluster_node_ids(self):
        return self.cluster_config.node_uris

    # Called by Role and in API
    def get_heartbeat_period(self):
        return self.cluster_config.heartbeat_period

    # Called by Role and in API
    def get_election_timeout(self):
        res = random.uniform(self.cluster_config.election_timeout_min,
                             self.cluster_config.election_timeout_max)
        return res

    # Called by Role
    def get_max_entries_per_message(self):
        return self.cluster_config.max_entries_per_message

    # Part of API 
    async def stop(self):
        await self.stop_role()

    async def stop_role(self):
        await self.role.stop()
        if self.role_async_handle:
            self.logger.debug("%s canceling scheduled task", self.get_my_uri())
            self.role_async_handle.cancel()
            self.role_async_handle = None

    # Called by Role
    async def start_campaign(self):
        await self.stop_role()
        self.role = Candidate(self)
        await self.role.start()
        self.logger.warning("%s started campaign term = %s", self.get_my_uri(), await self.log.get_term())

    # Called by Role
    async def win_vote(self, new_term):
        await self.stop_role()
        self.role = Leader(self, new_term)
        self.logger.warning("%s promoting to leader for term %s", self.get_my_uri(), new_term)
        await self.role.start()

    # Called by Role
    async def demote_and_handle(self, message=None):
        self.logger.warning("%s demoting from %s to follower", self.get_my_uri(), self.role)
        await self.stop_role()
        self.role = Follower(self)
        await self.role.start()
        if message and hasattr(message, 'leaderId'):
            self.logger.debug('%s message says leader is %s, adopting', self.get_my_uri(), message.leaderId)
            self.role.leader_uri = message.leaderId
        if message:
            self.logger.warning('%s reprocessing message as follower %s', self.get_my_uri(), message)
            return await self.inner_on_message(message)

    # Called by Role
    async def send_message(self, message):
        self.logger.debug("Sending message type %s to %s", message.get_code(), message.receiver)
        encoded = json.dumps(message, default=lambda o:o.__dict__)
        await self.pilot.send_message(message.receiver, encoded)

    # Called by Role
    async def send_response(self, message, response):
        self.logger.debug("Sending response type %s to %s", response.get_code(), response.receiver)
        encoded = json.dumps(message, default=lambda o:o.__dict__)
        encoded_reply = json.dumps(response, default=lambda o:o.__dict__)
        await self.pilot.send_response(response.receiver, encoded, encoded_reply)

    # Called by Role. This may seem odd, but it is done this
    # way to make it possible to protect against race conditions where a role
    # instance is shutting down but the timer that it has set fires during shutdown.
    # The actually happened during testing and it leads to some nasty logic conflicts.
    # Better to circumvent it by running the actual timers and callbacks in this
    # class, which never goes away.
    async def role_run_after(self, delay, target):
        loop = asyncio.get_event_loop()
        if self.role_async_handle:
            self.logger.debug('%s cancelling after target to %s', self.local_config.uri,
                        self.role_run_after_target)
            self.role_async_handle.cancel()
        self.logger.debug('%s setting run after target to %s', self.local_config.uri, target)
        self.role_run_after_target = target
        self.role_async_handle = loop.call_later(delay,
                                                  lambda target=target:
                                                  asyncio.create_task(self.role_after_runner(target)))

    # see comments above in role_run_after
    async def role_after_runner(self, target):
        if self.role.stopped:
            return
        await target()
        
    # Called by Role
    # see comments above in role_run_after
    async def cancel_role_run_after(self):
        if self.role_async_handle:
            self.role_async_handle.cancel()
            self.role_async_handle = None
        
    # Called by Role
    async def record_message_problem(self, message, problem):
        rec = dict(problem=problem, message=message)
        self.message_problem_history.append(rec)

    # Called by Role
    async def record_substate(self, substate):
        rec = dict(role=str(self.role), substate=substate, time=time.time())
        if self.log_substates:
            self.log_substates.debug("%s %s %s %s", self.get_my_uri(), rec['role'], rec['substate'], rec['time'])

    def get_message_problem_history(self, clear=False):
        res =  self.message_problem_history
        if clear:
            self.message_problem_history = []
        return res

