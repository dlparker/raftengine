import asyncio
import traceback
import logging
import random
import time
import json
from typing import Optional
from collections import defaultdict
    

from raftengine.api.types import RoleName, SubstateCode
from raftengine.api.events import EventType, EventHandler, ErrorEvent
from raftengine.api.events import RoleChangeEvent, TermChangeEvent, LeaderChangeEvent
from raftengine.api.events import MsgHandledEvent, MsgRecvEvent, MsgSentEvent
from raftengine.api.events import IndexChangeEvent, CommitChangeEvent
from raftengine.api.hull_api import CommandResult
from raftengine.messages.base_message import BaseMessage
from raftengine.messages.request_vote import RequestVoteMessage,RequestVoteResponseMessage
from raftengine.messages.pre_vote import PreVoteMessage,PreVoteResponseMessage
from raftengine.messages.append_entries import AppendEntriesMessage, AppendResponseMessage
from raftengine.roles.follower import Follower
from raftengine.roles.candidate import Candidate
from raftengine.roles.leader import Leader
from raftengine.api.pilot_api import PilotAPI
from raftengine.api.hull_api import HullAPI
from raftengine.api.events import EventType, EventHandler
from raftengine.api.hull_config import ClusterConfig, LocalConfig

class EventControl:

    def __init__(self):
        self.error_events = [EventType.error,]
        self.message_events = [EventType.msg_sent, EventType.msg_recv,
                               EventType.msg_handled]
        self.major_events = [EventType.role_change, EventType.term_change,
                             EventType.leader_change]
        self.common_events = [EventType.index_change, EventType.commit_change]

        self.active_events = []
        self.handlers = []
        self.handler_map = defaultdict(list)

    def add_handler(self, handler: EventHandler) -> None:
        if not handler in self.handlers:
            self.handlers.append(handler)
            for event_type in handler.events_handled():
                if event_type not in self.active_events:
                    self.active_events.append(event_type)
                if handler not in self.handler_map[event_type]:
                    self.handler_map[event_type].append(handler)

    def remove_handler(self, handler: EventHandler) -> None:
        if handler in self.handlers:
            self.handlers.remove(handler)
            for event_type in handler.events_handled():
                self.handler_map[event_type].remove(handler)
                if len(self.handler_map[event_type]) == 0:
                    self.active_events.remove(event_type)

    async def emit_error(self, error:str) -> None:
        my_type = EventType.error
        event = ErrorEvent(error)
        for handler in self.handler_map[my_type]:
            await handler.on_event(event)

    async def emit_sent_msg(self, msg:BaseMessage) -> None:
        my_type = EventType.msg_sent
        event = MsgSentEvent(msg)
        for handler in self.handler_map[my_type]:
            await handler.on_event(event)
            
    async def emit_recv_msg(self, msg:BaseMessage) -> None:
        my_type = EventType.msg_recv
        event = MsgRecvEvent(msg)
        for handler in self.handler_map[my_type]:
            await handler.on_event(event)

    async def emit_handled_msg(self, msg:BaseMessage, result: Optional[str] = None,
                               error: Optional[str] = None) -> None:
        my_type = EventType.msg_handled
        event = MsgHandledEvent(msg, result, error)
        for handler in self.handler_map[my_type]:
            await handler.on_event(event)
        
    async def emit_role_change(self, new_role: str) -> None:
        my_type = EventType.role_change
        event = RoleChangeEvent(new_role)
        for handler in self.handler_map[my_type]:
            await handler.on_event(event)

    async def emit_term_change(self, new_term:int) -> None:
        my_type = EventType.term_change
        event = TermChangeEvent(new_term)
        for handler in self.handler_map[my_type]:
            await handler.on_event(event)
        
    async def emit_leader_change(self, new_leader:str) -> None:
        my_type = EventType.leader_change
        event = LeaderChangeEvent(new_leader)
        for handler in self.handler_map[my_type]:
            await handler.on_event(event)
        
    async def emit_index_change(self, new_index):
        my_type = EventType.index_change
        event = IndexChangeEvent(new_index)
        for handler in self.handler_map[my_type]:
            await handler.on_event(event)

    async def emit_commit_change(self, new_commit):
        my_type = EventType.commit_change
        event = CommitChangeEvent(new_commit)
        for handler in self.handler_map[my_type]:
            await handler.on_event(event)
        
        
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
        self.leader_uri = None
        self.logger = logging.getLogger("Hull")
        self.role_async_handle = None
        self.role_run_after_target = None
        self.message_problem_history = []
        self.log_substates = logging.getLogger("Substates")
        self.event_control = EventControl()

    # Part of API
    def change_cluster_config(self, cluster_config: ClusterConfig):
        self.cluster_config = cluster_config
        
    # Part of API
    async def start(self):
        await self.role.start()
        if EventType.role_change in self.event_control.active_events:
            await self.event_control.emit_role_change(self.get_role_name())

    # Part of API
    def decode_message(self, in_message):
        mdict = json.loads(in_message)
        mtypes = [AppendEntriesMessage,AppendResponseMessage,
                  RequestVoteMessage,RequestVoteResponseMessage,
                  PreVoteMessage,PreVoteResponseMessage]
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
            if EventType.msg_recv in self.event_control.active_events:
                await self.event_control.emit_recv_msg(message)
        except:
            error = traceback.format_exc()
            self.logger.error(error)
            await self.record_message_problem(in_message, error)
            if EventType.error in self.event_control.active_events:
                await self.event_control.emit_error(error)
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
        if EventType.msg_handled in self.event_control.active_events:
            await self.event_control.emit_handled_msg(message, result=res, error=error)
        if error:
            if EventType.error in self.event_control.active_events:
                await self.event_control.emit_error(error)
            await self.record_message_problem(message, error)
        return res

    # Part of API
    async def run_command(self, command, timeout=1):
        if EventType.index_change in self.event_control.active_events:
            orig_log = await self.log.read()
        if EventType.commit_change in self.event_control.active_events:
            orig_commit = await self.log.get_commit_index()
        if self.role.role_name == RoleName.leader:
            result = await self.role.run_command(command, timeout=timeout)
        elif self.role.role_name == RoleName.follower:
            result = CommandResult(command, redirect=self.leader_uri)
        elif self.role.role_name == RoleName.candidate:
            result = CommandResult(command, retry=1)
        if EventType.index_change in self.event_control.active_events:
            new_log = await self.log.read()
            if new_log.index > orig_log.index:
                await self.event_control.emit_index_change(new_log.index)
        if EventType.commit_change in self.event_control.active_events:
            new_commit = await self.log.get_commit_index()
            if orig_commit != new_commit:
                await self.event_control.emit_commit_change(new_commit)
        return result
    
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
    
    # Called by Role
    async def set_leader_uri(self, uri):
        self.leader_uri = uri
        if EventType.leader_change in self.event_control.active_events:
            await self.event_control.emit_leader_change(uri)
    
    # Called by Role and in API
    async def get_term(self):
        return await self.log.get_term()

    # Called by Role and in API
    async def set_term(self, term):
        if EventType.term_change in self.event_control.active_events:
            await self.event_control.emit_term_change(term)
        return await self.log.set_term(term)

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
    def get_election_timeout_range(self):
        return self.cluster_config.election_timeout_min, self.cluster_config.election_timeout_max

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
        self.role = Candidate(self, use_pre_vote=self.cluster_config.use_pre_vote)
        await self.role.start()
        if EventType.role_change in self.event_control.active_events:
            await self.event_control.emit_role_change(self.get_role_name())
        self.logger.warning("%s started campaign term = %s pre_vote=%s", self.get_my_uri(),
                            await self.log.get_term(), self.cluster_config.use_pre_vote)

    # Called by Role
    async def win_vote(self, new_term):
        await self.stop_role()
        self.role = Leader(self, new_term, use_check_quorum=self.cluster_config.use_check_quorum)
        self.logger.warning("%s promoting to leader for term %s", self.get_my_uri(), new_term)
        await self.role.start()
        if EventType.role_change in self.event_control.active_events:
            await self.event_control.emit_role_change(self.get_role_name())

    # Called by Role
    async def demote_and_handle(self, message=None):
        self.logger.warning("%s demoting from %s to follower", self.get_my_uri(), self.role)
        await self.stop_role()
        self.role = Follower(self)
        await self.role.start()
        if EventType.role_change in self.event_control.active_events:
            await self.event_control.emit_role_change(self.get_role_name())
        if message and hasattr(message, 'leaderId'):
            self.logger.debug('%s message says leader is %s, adopting', self.get_my_uri(), message.leaderId)
            self.role.leader_uri = message.leaderId
            await self.set_leader_uri(message.leaderId)
        if message:
            self.logger.warning('%s reprocessing message as follower %s', self.get_my_uri(), message)
            return await self.inner_on_message(message)

    # Called by Role
    async def send_message(self, message):
        self.logger.debug("Sending message type %s to %s", message.get_code(), message.receiver)
        encoded = json.dumps(message, default=lambda o:o.__dict__)
        await self.pilot.send_message(message.receiver, encoded)
        if EventType.msg_sent in self.event_control.active_events:
            await self.event_control.emit_sent_msg(message)

    # Called by Role
    async def send_response(self, message, response):
        self.logger.debug("Sending response type %s to %s", response.get_code(), response.receiver)
        encoded = json.dumps(message, default=lambda o:o.__dict__)
        encoded_reply = json.dumps(response, default=lambda o:o.__dict__)
        await self.pilot.send_response(response.receiver, encoded, encoded_reply)
        if EventType.msg_sent in self.event_control.active_events:
            await self.event_control.emit_sent_msg(message)

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

