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
class CommandData:
    command: str
    user_context: str

class TimeoutTaskGroup(Exception):
    """Exception raised to terminate a task group due to timeout."""

class Commander:

    # Can be created one of two ways, but a newly submitted command, or during replay
    # of a stored but uncommitted command. In the former case a done_callback will
    # be suplied, but not in the later case. In the later case, a log_record will
    # be supplied, pulled from the log's pending record storage.
    def __init__(self, leader, command, user_context, done_callback=None, log_record=None):
        self.leader = leader
        self.command = command
        self.user_context = user_context
        self.done_callback = done_callback
        self.log_record = log_record
        self.logger = leader.logger
        self.done_condition = asyncio.Condition()
        self.timeout = 1
        self.terminated = False
        self.time_expired = False
        self.committed = False
        self.redirect_uri = None
        self.local_result = None
        self.local_error = None
        self.sent_messages = dict()
        self.reply_messages = dict()
        self.concurrences = 0
        
    async def start(self):
        term = await self.log.get_term()
        if self.log_record is None:
            udata = json.dumps(CommandData(command=self.command, user_context=self.user_context))
            new_rec = LogRec(term=term, user_data=udata)
            self.log_record = await self.log.save_pending(new_rec)
            # in case term changed, update it in record
            self.log_record.term = await self.log.get_term()

        proto_message = AppendEntriesMessage(sender=self.my_uri(),
                                                   receiver='',
                                                   term=await self.log.get_term(),
                                                   entries=[command,],
                                                   prevLogTerm=await self.log.get_last_term(),
                                                   prevLogIndex=await self.log.get_last_index())
        for uri in self.leader.hull.get_cluster_node_ids():
            if uri == self.leader.my_uri():
                continue
            message = AppendEntriesMessage(sender=proto_message.sender,
                                           receiver=uri,
                                           term=proto_message.term,
                                           entries=proto_message.entries,
                                           prevLogTerm=proto_message.prevLogTerm,
                                           prevLogIndex=proto_message.prevLogIndex)
            self.logger.info("sending %s", message)
            await self.leader.hull.send_message(message)
            await self.leader.record_sent_message(message)
            self.sent_messages[uri] = message

    async def wait_for_result(self, timeout):
        async def do_timeout(timeout):
            start_time = time.time()
            while self.done_count < self.expected_count:
                await asyncio.sleep(0.001)
            if time.time() - start_time >= timeout:
                self.time_expired = True
                raise TimeoutTaskGroup()
        async def check_done():
            with self.done_condition:
                await self.done_condition.wait()
                if self.terminated:
                    return
        try:
            async with asyncio.TaskGroup() as tg:
                tg.create_task(check_done())
                tg.create_task(do_timeout(self.timeout))
        except* TimeoutTaskGroup:
            pass

        if self.committed:
            await self.process_locally()
        return await self.compile_results()

    async def process_locally(self):
        result = None
        try:
            self.logger.info("%s applying command committed at index %d", self.my_uri(),
                             await self.log.get_last_index())
            processor = self.hull.get_processor()
            result,error = await processor.process_command(command)
        except Exception as e:
            self.local_error = traceback.format_exc()
        self.local_result = result
        if error:
            # we need to report this back to the caller, and resign, cause
            # we no longer have the most up to date log
            self.local_error = error
        
    async def compile_results(self):
        
        result = Command(command=command,
                         committed=self.committed,
                         timeout=self.time_expired,
                         result=self.local_result,
                         error=self.local_error,
                         redirect_url=self.redirect_url)
        if not self.committed and self.redirect is None:
            result.retry = True
        if committed:
            new_rec = LogRec(term=await self.log.get_term(),
                             user_data=json.dumps(result.__dict__))
            await self.log.commit_pending(self.log_record)

        return result
    
    async def apply_superceeded(self, message):
        # we are no longer leader
        if hasattr(message, "leaderId"):
            self.redirect_uri = message.leaderId
        self.terminated = True
        with self.done_condition:
            self.done_condition.notify()

    async def record_replica_command_error(self, message):
        # This spot will have to have some code in it to figure out what to
        # do with the fact that it had an error. A hooman prolly needs to
        # fix something.
        pass

    async def apply_committed_command(self):
        self.committed = True
        self.terminated = True
        with self.done_condition:
            self.done_condition.notify()

    async def apply_consensus_failed(self):
        self.terminated = True
        with self.done_condition:
            self.done_condition.notify()
        
    async def is_process_command_response(self, message):
        if  (message.term == term
             and message.lastLogIndex == await self.leader.log.get_last_index()
             and message.lastLogTerm == await self.leader.log.get_last_term()):
            return True
        return False
    
    async def process_command_response(self, message):
        term = await self.log.get_term()
        if message.term > term:
            await self.apply_superceeded()
            return
        self.reply_messages[uri] = message
        if not (message.term == term
                and message.myLastLogIndex == await self.leader.log.get_last_index()
                and message.myLastLogTerm == await self.leader.log.get_last_term()):
            # Recipient found something amis, term or details of previous
            # record in their log. They did not apply the command, so
            # don't count this one in committed calc
            return
        results = json.loads(message.results)
        error = results[0].error
        if (error):
            await self.record_replica_command_error(message)
            return
        else:
            self.concurrences += 1
        # Include self in test for majority concensus
        if self.concurrences + 1 >= len(self.sent_messages) / 2:
            #concensus reached for commit
            return await self.apply_committed_command()
        remaining = len(self.sent_messages) - len(self.reply_messages)
        needed = len(self.sent_messages) - self.concurrences + 1
        if needed > remaining:
            # concensus not possible
            return await self.apply_consensus_failed()
        
@dataclass
class DialogTracker:
    sent_message: AppendEntriesMessage
    sent_time: int = None
    reply_message: AppendResponseMessage = None
    replied_time: int = None
    
    nack: BaseMessage | None = None

@dataclass
class FollowerTracker:
    uri: str 
    pending: List[DialogTracker]
    history: List[DialogTracker]
    msg_count: int = 0
    reply_count: int = 0


        
@dataclass
class PairTracker:
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
    dialogs: Dict[str, PairTracker]  | None
    reject_msg: AppendResponseMessage | None = None


class CommandResult:

    def __init__(self, command, result=None, committed=False,
                 redirect=None, retry=None, logRec=None, error=None, timeout=False):
        self.command = command
        self.result = result
        self.committed = committed
        self.redirect = redirect
        self.retry = retry
        self.logRec = logRec
        self.error = error
        self.timeout = timeout
        
class Leader(BaseState):

    def __init__(self, hull, term):
        super().__init__(hull, StateCode.leader)
        self.last_broadcast_time = 0
        self.pending_command = None
        self.logger = logging.getLogger("Leader")
        self.follower_trackers = dict()
        self.follower_pending = dict()
        self.follower_history = dict()
        for uri in self.hull.get_cluster_node_ids():
            self.follower_trackers[uri] = FollowerTracker(uri=uri, pending=[], history=[])
                
    async def start(self):
        await super().start()
        await self.run_after(self.hull.get_heartbeat_period(), self.send_heartbeats)
        await self.send_heartbeats()

    async def apply_command(self, command, timeout=1.0):
        if self.pending_command:
            self.logger.info("%s waiting for completion of pending command", self.my_uri())
            start_time = time.time()
            while self.pending_command and time.time() - start_time < timeout:
                await asyncio.sleep(0.001)
            if self.pending_command:
                msg = f'command already pending not completed in {timeout} seconds, command was'
                msg += f" {self.pending_command.commands}"
                result = CommandResult(command=command, error=msg)
                return result

        self.logger.info("%s starting command sequence for index %d", self.my_uri(),
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
            self.logger.info("%s applying command committed at index %d", self.my_uri(),
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
        result = CommandResult(command=command, result=result, committed=error is not None, error = error)
        return result
        

    async def prepare_command(self, command):
        message = AppendEntriesMessage(sender=self.my_uri(),
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
                                 self.my_uri())
                return False, tracker.reject_msg.leaderId 
            if tracker.reject_msg.leaderId != self.my_uri():
                self.logger.info("%s no longer leader, returning redirect to %s",
                                 self.my_uri(), tracker.reject_msg.leaderId)
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
            if uri == self.my_uri():
                continue
            message = AppendEntriesMessage(sender=tracker.proto_msg.sender,
                                           receiver=uri,
                                           term=tracker.proto_msg.term,
                                           entries=tracker.proto_msg.entries,
                                           prevLogTerm=tracker.proto_msg.prevLogTerm,
                                           prevLogIndex=tracker.proto_msg.prevLogIndex)
            dialog = PairTracker(message,
                                   time.time())
            tracker.dialogs[uri] = dialog
            self.logger.info("sending %s", message)
            await self.hull.send_message(message)
            await self.record_sent_message(message)
        self.last_broadcast_time = time.time()

    async def process_command_response(self, message):
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
            if uri == self.my_uri():
                continue
            if tracker.dialogs[uri].ack != None:
                acked += 1
        if acked  + 1 > len(tracker.dialogs) / 2: # this server counts too
            self.logger.info('%s got consensus on index %d, applying command', self.my_uri(),
                             message.prevLogIndex + 1)
            # current state is "committed" as defined in raft paper, command can
            # be applied
            self.pending_command.finished = True
        
    async def process_heartbeat_response(self, message):
        if message.prevLogIndex > message.myPrevLogIndex:
            await self.catch_follower_up(message)
            return
        return
    
    async def on_append_entries_response(self, message):
        await self.record_received_message(message)
        
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
            self.logger.debug("%s resched heartbeats time left %f", self.my_uri, remaining_time)
            await self.run_after(remaining_time, self.send_heartbeats)
            return
        if self.pending_command:
            wait_time = self.hull.get_heartbeat_period() / 50.0
            self.logger.debug("%s pending command, resched heartbeats time left %f",
                              self.my_uri, wait_time)
            await self.run_after(wait_time, self.send_heartbeats)
            return
        for uri in self.hull.get_cluster_node_ids():
            if uri == self.my_uri():
                continue
            message = AppendEntriesMessage(sender=self.my_uri(),
                                           receiver=uri,
                                           term=await self.log.get_term(),
                                           entries=[],
                                           prevLogTerm=await self.log.get_term(),
                                           prevLogIndex=await self.log.get_last_index())
            self.logger.debug("%s sending heartbeat to %s", message.sender, message.receiver)
            await self.hull.send_message(message)
            await self.record_sent_message(message)
            self.last_broadcast_time = time.time()
        
    async def catch_follower_up(self, message):
        if message.prevLogIndex == message.myPrevLogIndex:
            return
        # get the first log record they are missing, send that one
        rec = await self.log.read(message.myPrevLogIndex + 1)
        command = json.loads(rec.user_data)['command']
        entries = [command,]
        message = AppendEntriesMessage(sender=self.my_uri(),
                                       receiver=message.sender,
                                       term=await self.log.get_term(),
                                       entries=entries,
                                       prevLogTerm=await self.log.get_term(),
                                       prevLogIndex=await self.log.get_last_index())
        self.logger.info("sending catchup %s", message)
        await self.record_sent_message(message)
        await self.hull.send_message(message)

        
    async def term_expired(self, message):
        if self.pending_command:
            self.logger.warning('%s term expired when expecting command response, %s',
                                self.my_uri(), message)
            await self.process_command_response(message)
            return None
        await self.log.set_term(message.term)
        await self.hull.demote_and_handle(message)
        # don't reprocess message
        return None

    async def record_sent_message(self, message):
        tracker = self.follower_trackers.get(message.receiver, None)
        if tracker:
            dialog = DialogTracker(sent_message=message, sent_time=time.time())
            tracker.pending.append(dialog)

    async def record_received_message(self, message):
        tracker = self.follower_trackers.get(message.sender, None)
        if tracker:
            # To keep pending clean, we just discard messages that don't
            # match. In all normal sequences there will not be a mismatch.
            # The cases where that doesn't happend are rare, just when
            # a single message or two get dropped and then things get better.
            # There is no value in tracking these cases that warrants the
            # cost in code complexity and especially testing effort.
            pending = tracker.pending
            tracker.pending = []
            for rec in tracker.pending:
                if (rec.sent_message.lastLogIndex == message.lastLogIndex
                    and rec.sent_message.lastLogTerm == message.lastLogTerm):
                    rec.reply_message = message
                    rec.reply_time = time.time()
                    if len(tracker.history) >= 100:
                        tracker.history.pop(0)
                    tracker.history.append(rec)
                                
    def my_uri(self):
        return self.hull.get_my_uri()



