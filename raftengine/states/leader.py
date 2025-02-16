import logging
import asyncio
import time
import json
import traceback
from dataclasses import dataclass
from typing import Dict, List, Any
from enum import Enum
from raftengine.api.types import StateCode, SubstateCode
from raftengine.log.log_api import LogRec
from raftengine.messages.append_entries import AppendEntriesMessage,AppendResponseMessage
from raftengine.messages.base_message import BaseMessage
from raftengine.states.base_state import BaseState

    
@dataclass
class DialogTracker:
    sent_msg: BaseMessage
    sent_time: int = None
    replied_time: int = None
    ack: BaseMessage | None = None
    nack: BaseMessage | None = None

@dataclass
class CommandTracker:
    command: str
    finished: bool
    rejected: bool
    proto_msg: AppendEntriesMessage
    dialogs: Dict[str, DialogTracker]  | None
    reject_msg: AppendResponseMessage | None = None

@dataclass
class FollowerTracker:
    uri: str 
    msgs: int = 0
    replies: int = 0
    last_dialog = DialogTracker

class CommandResult:

    def __init__(self, command, result=None, complete=False, redirect=None, retry=None, logRec=None, error=None):
        self.command = command
        self.result = result
        self.complete = complete
        self.redirect = redirect
        self.retry = retry
        self.logRec = logRec
        self.error = error
        
class Leader(BaseState):

    def __init__(self, hull, term):
        super().__init__(hull, StateCode.leader)
        self.last_broadcast_time = 0
        self.pending_command = None
        self.logger = logging.getLogger("Leader")
        self.follower_trackers = dict()
        for uri in self.hull.get_cluster_node_ids():
            self.follower_trackers[uri] = FollowerTracker(uri=uri)
                
    async def start(self):
        await super().start()
        await self.run_after(self.hull.get_heartbeat_period(), self.send_heartbeats)
        await self.send_heartbeats()

    async def apply_command(self, command, timeout=1.0):
        if self.pending_command:
            self.logger.info("%s waiting for completion of pending command", self.hull.get_my_uri())
            start_time = time.time()
            while self.pending_command and time.time() - start_time < timeout:
                await asyncio.sleep(0.001)
            if self.pending_command:
                msg = f'command already pending not completed in {timeout} seconds, command was'
                msg += f" {self.pending_command.commands}"
                result = CommandResult(command=command, error=msg)
                return result

        self.logger.info("%s starting command sequence for index %d", self.hull.get_my_uri(),
                         await self.log.get_last_index())

        await self.prepare_command(command)
        await self.broadcast_command()

        try:
            done, redirect = await self.collect_command_result(timeout) # raises on Timeout
        except:
            error = traceback.format_exc()
            result = CommandResult(command=command, error = error)
            self.pending_command = None
            return result
            
        if redirect is not None or not done:
            if redirect is None:
                retry = 1
            else:
                retry = None
            result = CommandResult(command=command, redirect=redirect, retry=retry)
            self.pending_command = None
            return result

        try:
            self.logger.info("%s applying command committed at index %d", self.hull.get_my_uri(),
                             await self.log.get_last_index())
            processor = self.hull.get_processor()
            result,error = await processor.process_command(command)
        except Exception as e:
            error = traceback.format_exc()
            result = CommandResult(command=command, error = error)
            self.pending_command = None
            return result
            
        run_result = dict(command=command,
                          result=result,
                          error=error)
        new_rec = LogRec(term=await self.log.get_term(),
                         user_data=json.dumps(run_result))
        await self.log.append([new_rec,])
        self.pending_command = None
        result = CommandResult(command=command, result=result, complete=error is not None, error = error)
        return result
        

    async def prepare_command(self, command):
        message = AppendEntriesMessage(sender=self.hull.get_my_uri(),
                                       receiver='',
                                       term=await self.log.get_term(),
                                       entries=[command,],
                                       prevLogTerm=await self.log.get_last_term(),
                                       prevLogIndex=await self.log.get_last_index())
        
        self.pending_command = CommandTracker(command=command,
                                              finished=False,
                                              rejected=False,
                                              proto_msg=message,
                                              dialogs=dict())

    async def command_done_checker(self):
        tracker = self.pending_command
        while not tracker.finished and not tracker.rejected:
            try:
                await asyncio.sleep(0.0001)
            except asyncio.CancelledError:
                return False, None
        if tracker.rejected:
            if tracker.reject_msg is None:
                return False, None
            if tracker.reject_msg.get_code() != AppendResponseMessage:
                self.logger.info("%s no longer leader, returning retry (leader unknown)",
                                 self.hull.get_my_uri())
                return False, tracker.reject_msg.leaderId 
            if tracker.reject_msg.leaderId != self.hull.get_my_uri():
                self.logger.info("%s no longer leader, returning redirect to %s",
                                 self.hull.get_my_uri(), tracker.reject_msg.leaderId)
                return False, tracker.reject_msg.leaderId 
        return True, None
        
    async def collect_command_result(self, timeout):
        try:
            done, redirect = await asyncio.wait_for(asyncio.create_task(
                self.command_done_checker()), timeout=timeout)
        except asyncio.TimeoutError:
            self.pending_command = None
            msg = f'Requested command sequence not completed in {timeout} seconds'
            raise Exception(msg)
        return done, redirect
    
    async def broadcast_command(self):
        tracker = self.pending_command
        for uri in self.hull.get_cluster_node_ids():
            if uri == self.hull.get_my_uri():
                continue
            message = AppendEntriesMessage(sender=tracker.proto_msg.sender,
                                           receiver=uri,
                                           term=tracker.proto_msg.term,
                                           entries=tracker.proto_msg.entries,
                                           prevLogTerm=tracker.proto_msg.prevLogTerm,
                                           prevLogIndex=tracker.proto_msg.prevLogIndex)
            dialog = DialogTracker(message,
                                   time.time())
            tracker.dialogs[uri] = dialog
            self.logger.info("sending %s", message)
            await self.hull.send_message(message)
            # update the per follower general records
            follower_tracker = self.follower_trackers[uri]
            gen_dialog = DialogTracker(message,
                                   time.time())
            follower_tracker.last_dialog = gen_dialog
        self.last_broadcast_time = time.time()

    async def process_command_response(self, message):
        follower_tracker = self.follower_trackers[message.sender]
        gen_dialog = follower_tracker.last_dialog
        gen_dialog.replied_time = time.time()
        cmd_dialog = self.pending_command.dialogs[message.sender]
        cmd_dialog.replied_time = time.time()
        if message.term > await self.log.get_term():
            # we are no longer leader
            self.pending_command.rejected = True
            self.pending_command.reject_msg = message
            cmd_dialog.nack = message
            return
        
        cmd_dialog.ack = message
        tracker = self.pending_command
        acked = 0
        # count the concurrences
        for uri in self.hull.get_cluster_node_ids():
            if uri == self.hull.get_my_uri():
                continue
            if tracker.dialogs[uri].ack != None:
                acked += 1
        if acked  + 1 > len(tracker.dialogs) / 2: # this server counts too
            self.logger.info('%s got consensus on index %d, applying command', self.hull.get_my_uri(),
                             message.prevLogIndex + 1)
            # current state is "committed" as defined in raft paper, command can
            # be applied
            self.pending_command.finished = True
        
    async def process_heartbeat_response(self, message):
        follower_tracker = self.follower_trackers[message.sender]
        dialog = follower_tracker.last_dialog
        dialog.replied_time = time.time()
        if message.prevLogIndex > message.myPrevLogIndex:
            dialog.nack = message
            await self.catch_follower_up(message)
            return
        dialog.ack = message
        return
    
    async def on_append_entries_response(self, message):
        if (self.pending_command
            and self.pending_command.proto_msg.prevLogIndex == message.prevLogIndex):
            # this is a reply to the pending command, process it accordingly
            await self.process_command_response(message)
            return

        # We don't do this check first because if we got it as a command
        # reply, we have to tell user. Otherwise we just retire
        if message.term > await self.log.get_term():
            await self.log.set_term(message.term)
            await self.hull.demote_and_handle(None)
            return
        # this was a heartbeat
        await self.process_heartbeat_response(message)
        return
    
    async def send_heartbeats(self):
        silent_time = time.time() - self.last_broadcast_time
        remaining_time = self.hull.get_heartbeat_period() - silent_time
        if  remaining_time > 0:
            self.logger.debug("%s resched heartbeats time left %f", self.hull.get_my_uri, remaining_time)
            await self.run_after(remaining_time, self.send_heartbeats)
            return
        if self.pending_command:
            wait_time = self.hull.get_heartbeat_period() / 50.0
            self.logger.debug("%s pending command, resched heartbeats time left %f",
                              self.hull.get_my_uri, wait_time)
            await self.run_after(wait_time, self.send_heartbeats)
            return
        for uri in self.hull.get_cluster_node_ids():
            if uri == self.hull.get_my_uri():
                continue
            message = AppendEntriesMessage(sender=self.hull.get_my_uri(),
                                           receiver=uri,
                                           term=await self.log.get_term(),
                                           entries=[],
                                           prevLogTerm=await self.log.get_term(),
                                           prevLogIndex=await self.log.get_last_index())
            self.logger.debug("%s sending heartbeat to %s", message.sender, message.receiver)
            await self.hull.send_message(message)
            follower_tracker = self.follower_trackers[uri]
            follower_tracker.last_dialog = DialogTracker(message,
                                                         time.time())
        self.last_broadcast_time = time.time()
        
    async def catch_follower_up(self, message):
        if message.prevLogIndex == message.myPrevLogIndex:
            return
        # get the first log record they are missing, send that one
        rec = await self.log.read(message.myPrevLogIndex + 1)
        command = json.loads(rec.user_data)['command']
        entries = [command,]
        message = AppendEntriesMessage(sender=self.hull.get_my_uri(),
                                       receiver=message.sender,
                                       term=await self.log.get_term(),
                                       entries=entries,
                                       prevLogTerm=await self.log.get_term(),
                                       prevLogIndex=await self.log.get_last_index())
        self.logger.info("sending catchup %s", message)
        await self.hull.send_message(message)
        follower_tracker = self.follower_trackers[message.sender]
        follower_tracker.last_dialog = DialogTracker(message,
                                                     time.time())
        
    async def term_expired(self, message):
        if self.pending_command:
            self.logger.warning('%s term expired when expeecting command response, %s',
                                self.hull.get_my_uri(), message)
            await self.process_command_response(message)
            return None
        await self.log.set_term(message.term)
        await self.hull.demote_and_handle(message)
        # don't reprocess message
        return None





