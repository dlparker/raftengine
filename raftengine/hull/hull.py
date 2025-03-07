import asyncio
import traceback
import logging
import random
import time
import json

from raftengine.api.types import StateCode, SubstateCode
from raftengine.messages.base_message import BaseMessage
from raftengine.messages.request_vote import RequestVoteMessage,RequestVoteResponseMessage
from raftengine.messages.append_entries import AppendEntriesMessage, AppendResponseMessage
from raftengine.states.follower import Follower
from raftengine.states.candidate import Candidate
from raftengine.states.leader import Leader, CommandResult
from raftengine.states.leader import CommandResult
from raftengine.api.pilot_api import PilotAPI
from raftengine.api.hull_api import HullAPI

class Hull(HullAPI):

    def __init__(self, cluster_config, local_config, pilot: PilotAPI):
        self.cluster_config = cluster_config
        self.local_config = local_config
        if not isinstance(pilot, PilotAPI):
            raise Exception('Must supply a raftengine.hull.api.PilotAPI implementation')
        self.pilot = pilot
        self.log = pilot.get_log()
        self.state = Follower(self)
        self.logger = logging.getLogger("Hull")
        self.state_async_handle = None
        self.state_run_after_target = None
        self.message_problem_history = []
        self.log_substates = logging.getLogger("Substates")

    # Part of API
    async def start(self):
        await self.state.start()

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
            res = await self.state.on_message(message)
        except Exception as e:
            error = traceback.format_exc()
            self.logger.error(error)
        if error:
            await self.record_message_problem(message, error)
        return res

    # Part of API
    async def run_command(self, command, timeout=1):
        if self.state.state_code == StateCode.leader:
            return await self.state.run_command(command, timeout=timeout)
        elif self.state.state_code == StateCode.follower:
            return CommandResult(command, redirect=self.state.leader_uri)
        elif self.state.state_code == StateCode.candidate:
            return CommandResult(command, retry=1)
    
    # Called by State
    def get_log(self):
        return self.log

    # Called by State
    def get_state_code(self):
        return self.state.state_code

    # Called by State
    def get_my_uri(self):
        return self.local_config.uri
        
    # Called by State
    def get_processor(self):
        return self.pilot
    
    # Called by State and in API
    async def get_term(self):
        return await self.log.get_term()

    # Called by State and in API
    def get_cluster_node_ids(self):
        return self.cluster_config.node_uris

    # Called by State and in API
    def get_heartbeat_period(self):
        return self.cluster_config.heartbeat_period

    # Called by State and in API
    def get_election_timeout(self):
        res = random.uniform(self.cluster_config.election_timeout_min,
                             self.cluster_config.election_timeout_max)
        return res

    # Part of API 
    async def stop(self):
        await self.stop_state()

    async def stop_state(self):
        await self.state.stop()
        if self.state_async_handle:
            self.logger.debug("%s canceling scheduled task", self.get_my_uri())
            self.state_async_handle.cancel()
            self.state_async_handle = None

    # Called by State
    async def start_campaign(self):
        await self.stop_state()
        self.state = Candidate(self)
        await self.state.start()
        self.logger.warning("%s started campaign term = %s", self.get_my_uri(), await self.log.get_term())

    # Called by State
    async def win_vote(self, new_term):
        await self.stop_state()
        self.state = Leader(self, new_term)
        self.logger.warning("%s promoting to leader for term %s", self.get_my_uri(), new_term)
        await self.state.start()

    # Called by State
    async def demote_and_handle(self, message=None):
        self.logger.warning("%s demoting from %s to follower", self.get_my_uri(), self.state)
        await self.stop_state()
        self.state = Follower(self)
        await self.state.start()
        if message and hasattr(message, 'leaderId'):
            self.logger.debug('%s message says leader is %s, adopting', self.get_my_uri(), message.leaderId)
            self.state.leader_uri = message.leaderId
        if message:
            self.logger.warning('%s reprocessing message as follower %s', self.get_my_uri(), message)
            return await self.inner_on_message(message)

    # Called by State
    async def send_message(self, message):
        self.logger.debug("Sending message type %s to %s", message.get_code(), message.receiver)
        encoded = json.dumps(message, default=lambda o:o.__dict__)
        await self.pilot.send_message(message.receiver, encoded)

    # Called by State
    async def send_response(self, message, response):
        self.logger.debug("Sending response type %s to %s", response.get_code(), response.receiver)
        encoded = json.dumps(message, default=lambda o:o.__dict__)
        encoded_reply = json.dumps(response, default=lambda o:o.__dict__)
        await self.pilot.send_response(response.receiver, encoded, encoded_reply)

    async def state_after_runner(self, target):
        if self.state.stopped:
            return
        await target()
        
    # Called by State
    async def state_run_after(self, delay, target):
        loop = asyncio.get_event_loop()
        if self.state_async_handle:
            self.logger.debug('%s cancelling after target to %s', self.local_config.uri,
                        self.state_run_after_target)
            self.state_async_handle.cancel()
        self.logger.debug('%s setting run after target to %s', self.local_config.uri, target)
        self.state_run_after_target = target
        self.state_async_handle = loop.call_later(delay,
                                                  lambda target=target:
                                                  asyncio.create_task(self.state_after_runner(target)))

    # Called by State
    async def cancel_state_run_after(self):
        if self.state_async_handle:
            self.state_async_handle.cancel()
            self.state_async_handle = None
        
    # Called by State
    async def record_message_problem(self, message, problem):
        rec = dict(problem=problem, message=message)
        self.message_problem_history.append(rec)

    # Called by State
    async def record_substate(self, substate):
        rec = dict(state=str(self.state), substate=substate, time=time.time())
        if self.log_substates:
            self.log_substates.debug("%s %s %s %s", self.get_my_uri(), rec['state'], rec['substate'], rec['time'])

