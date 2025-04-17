import logging 
import asyncio
import time
import json
import traceback
from dataclasses import dataclass
from typing import Dict, List, Any
from enum import Enum
from raftengine.api.types import StateCode, SubstateCode
from raftengine.api.log_api import LogRec, RecordCode
from raftengine.api.hull_api import CommandResult
from raftengine.messages.append_entries import AppendEntriesMessage,AppendResponseMessage
from raftengine.messages.base_message import BaseMessage
from raftengine.roles.base_role import BaseRole

@dataclass
class FollowerTracker:
    uri: str 
    nextIndex: int = 0
    lastSentIndex: int = 0
    matchIndex: int = 0
    msg_count: int = 0
    reply_count: int = 0
    last_msg_time: int = 0
    last_reply_time: int = 0

        
class TimeoutTaskGroup(Exception):
    """Exception raised to terminate a task group due to timeout."""

class CommandWaiter:

    def __init__(self, leader, log, orig_log_record, timeout=1.0):
        self.leader = leader
        self.log = log
        self.orig_log_record = orig_log_record
        self.timeout = timeout
        self.done_condition = asyncio.Condition()
        self.committed = False
        self.time_expired = False
        self.local_error = None
        self.result = None

    async def wait_for_result(self):

        async def do_timeout(timeout):
            start_time = time.time()
            while not self.committed and not self.local_error:
                await asyncio.sleep(0.001)
                if time.time() - start_time >= timeout:
                    self.time_expired = True
                    self.leader.logger.warning("%s !!!!!!!!!! Timeout on command ", self.leader.my_uri())
                    raise TimeoutTaskGroup(f"timeout after {timeout}")
            
        async def check_done():
            while not self.time_expired and not self.result:
                async with self.done_condition:
                    await self.done_condition.wait()
                    self.leader.logger.debug("%s check_done awake from command ", self.leader.my_uri())
            return self.result

        try:
            async with asyncio.TaskGroup() as tg:
                tg.create_task(check_done())
                tg.create_task(do_timeout(self.timeout))
                self.leader.logger.debug("%s scheduled timeout for %f and check_done", self.leader.my_uri(), self.timeout)
        except* TimeoutTaskGroup:
            self.leader.logger.debug("%s timeout exception", self.leader.my_uri())
            hull = self.leader.hull
            leader_uri = None
            if hull.role != self.leader:
                if hasattr(hull.role, 'leader_uri'):
                    leader_uri = hull.role.leader_uri
                self.leader.logger.debug("%s after timeout exception am no longer leader! maybe %s?",
                                         self.leader.my_uri(), leader_uri)
                self.result = CommandResult(command=self.orig_log_record.command,
                                            committed=False,
                                            redirect=leader_uri)
            else:
                self.leader.logger.debug("%s command timeout exception",
                                         self.leader.my_uri())
                self.result = CommandResult(command=self.orig_log_record.command,
                                            committed=False,
                                            timeout_expired=True)
            
        return self.result

    async def handle_run_result(self, command_result, error_data):
        if not error_data:
            self.committed = True
        self.local_error = error_data
        result = CommandResult(command=self.orig_log_record.command,
                               committed=self.committed,
                               timeout_expired=False,
                               result=command_result,
                               error=error_data,
                               redirect=None)
        if error_data:
            await self.leader.hull.record_substate(SubstateCode.failed_command)
        else:
            await self.leader.hull.record_substate(SubstateCode.committing_command)
            self.orig_log_record.committed = True
            self.orig_log_record.result = command_result
            new_rec = await self.log.replace(self.orig_log_record)
        self.result = result
        async with self.done_condition:
            self.done_condition.notify()
        return 
        
class Leader(BaseRole):

    def __init__(self, hull, term):
        super().__init__(hull, StateCode.leader)
        self.last_broadcast_time = 0
        self.logger = logging.getLogger("Leader")
        self.follower_trackers = dict()
        self.command_waiters = dict()
        self.max_entries_per_message = 9 # should this be configurable?
                
    async def start(self):
        await super().start()
        for uri in self.hull.get_cluster_node_ids():
            tracker = await self.tracker_for_follower(uri)
        await self.run_after(self.hull.get_heartbeat_period(), self.scheduled_send_heartbeats)
        start_record = LogRec(code=RecordCode.term_start,
                              term=await self.log.get_term(),
                              leader_id=self.my_uri())
        the_record = await self.log.append(start_record)
        await self.broadcast_log_record(the_record)

    async def run_command(self, command, timeout=1.0, serial=None):
        # first save it in the log
        if serial is None:
            serial = await self.log.get_last_index() + 1
        raw_rec = LogRec(command=command, term=await self.log.get_term(),
                         leader_id=self.my_uri(), serial=serial)
        log_rec = await self.log.append(raw_rec)
        self.logger.debug("%s saved log record at index %d", self.my_uri(), log_rec.index)
        # now send it to everybody
        await self.hull.record_substate(SubstateCode.preparing_command)
        await self.broadcast_log_record(log_rec)
        waiter = CommandWaiter(self, log=self.log, orig_log_record=log_rec, timeout=timeout)
        self.command_waiters[log_rec.index] = waiter
        self.logger.info("%s waiting for completion of pending command", self.my_uri())
        result = await waiter.wait_for_result()
        return result

    async def broadcast_log_record(self, log_record):
        prevLogIndex = 0
        prevLogTerm = 0
        if log_record.index > 1:
            prev_rec = await self.log.read(log_record.index - 1)
            prevLogIndex = prev_rec.index
            prevLogTerm = prev_rec.term
        term = await self.log.get_term()
        commit_index = await self.log.get_commit_index()
        proto_message = AppendEntriesMessage(sender=self.my_uri(),
                                             receiver='',
                                             term=term,
                                             entries=[log_record,],
                                             prevLogTerm=prevLogTerm,
                                             prevLogIndex=prevLogIndex,
                                             commitIndex=commit_index)
        if log_record.code == RecordCode.client_command:
            await self.hull.record_substate(SubstateCode.broadcasting_command)
        if log_record.code == RecordCode.term_start:
            await self.hull.record_substate(SubstateCode.broadcasting_term_start)
        for uri in self.hull.get_cluster_node_ids():
            if uri == self.my_uri():
                continue
            tracker = self.follower_trackers[uri]
            if tracker.nextIndex < log_record.index:
                # we don't send the new record unless the
                # follower is up to date, it will get
                # a copy once it gets caught up
                continue
            tracker.lastSentIndex = log_record.index
            message = AppendEntriesMessage.from_dict(proto_message.__dict__)
            message.receiver = uri
            self.logger.info("broadcast command sending %s", message)
            await self.hull.send_message(message)
            await self.record_sent_message(message)

    async def scheduled_send_heartbeats(self):
        await self.send_heartbeats()
        await self.run_after(self.hull.get_heartbeat_period(), self.scheduled_send_heartbeats)
        
    async def send_heartbeats(self):
        entries = []
        term = await self.log.get_term()
        my_uri = self.my_uri()
        last_term = await self.log.get_last_term()
        last_index = await self.log.get_last_index()
        commit_index = await self.log.get_commit_index()
        for uri in self.hull.get_cluster_node_ids():
            if uri == self.my_uri():
                continue
            message = AppendEntriesMessage(sender=my_uri,
                                           receiver=uri,
                                           term=term,
                                           entries=entries,
                                           prevLogTerm=last_term,
                                           prevLogIndex=last_index,
                                           commitIndex=commit_index)
            self.logger.debug("%s sending heartbeat %s", my_uri, message)
            await self.hull.send_message(message)
            await self.record_sent_message(message)
            self.last_broadcast_time = time.time()
        
    async def on_append_entries_response(self, message):
        tracker = self.follower_trackers[message.sender]
        self.logger.debug('handling response %s', message)
        self.logger.debug('follower=%s at message beginning tracker.nextIndex = %d tracker.matchIndex = %d',
                          message.sender, tracker.nextIndex, tracker.matchIndex)
        await self.record_received_message(message)
        if not message.success:
            # there are async issues when networks are flaky, this could be a rejection of an old
            # append, so check what we sent in this message against what we recorded that we
            # sent in the last message
            await self.send_backdown(message)
            self.logger.debug('After backdown to %s tracker.nextIndex = %d tracker.matchIndex = %d',
                              message.sender, tracker.nextIndex, tracker.matchIndex)
            return
        if message.maxIndex == tracker.nextIndex:
            tracker.nextIndex += 1
            tracker.matchIndex = message.maxIndex
            self.logger.debug('Success to %s upped tracker.nextIndex to %d',
                              message.sender, tracker.nextIndex)
        if tracker.nextIndex > await self.log.get_last_index():
            self.logger.debug('After success to %s tracker.nextIndex = %d tracker.matchIndex = %d',
                              message.sender, tracker.nextIndex, tracker.matchIndex)
            if tracker.matchIndex > await self.log.get_commit_index():
                # see if this message completes the majority saved requirement
                # that defines commit at the cluster level, and apply it
                # if so.
                log_rec = await self.log.read(tracker.matchIndex)
                await self.record_commit_checker(log_rec)
            return

        await self.send_catchup(message)
        self.logger.debug('After catchup %s tracker.nextIndex = %d tracker.matchIndex = %d',
                          message.sender, tracker.nextIndex, tracker.matchIndex)
        
    async def send_backdown(self, message):
        uri = message.sender
        tracker = self.follower_trackers[uri]
        pnum = -1
        if message.maxIndex < message.prevLogIndex:
            # Follower is telling us to skip a bit, brother,
            # because his max stored log record index is less than
            # our current attempt level. An optimization, not
            # strictly necessary. It also doesn't guarantee
            # a match, his max index record might be for a different
            # term, but we should at least start backing down there
            send_index = message.maxIndex + 1
            tracker.nextIndex = send_index + 1
            pnum = 2
        else:
            send_index = message.prevLogIndex
            tracker.nextIndex = send_index + 1
            pnum = 3
        prevLogIndex = 0
        prevLogTerm = 0
        if send_index > 1:
            pre_rec = await self.log.read(send_index - 1)
            prevLogIndex = pre_rec.index
            prevLogTerm = pre_rec.term
        tracker.lastSentIndex = send_index
        rec = await self.log.read(send_index)
        rec.committed = False
        entries = [rec,]
        message = AppendEntriesMessage(sender=self.my_uri(),
                                       receiver=uri,
                                       term=await self.log.get_term(),
                                       entries=entries,
                                       prevLogTerm=prevLogTerm,
                                       prevLogIndex=prevLogIndex,
                                       commitIndex=await self.log.get_commit_index())
        self.logger.info("sending backdown %s", message)
        await self.hull.record_substate(SubstateCode.sending_backdown)
        await self.record_sent_message(message)
        await self.hull.send_message(message)
    
    async def send_catchup(self, message):
        uri = message.sender
        tracker = self.follower_trackers[uri]
        # Due to asnyc nature of this code, it is possible for one
        # message from the leader to get processed by the follower
        # and trigger a reply before the previous message reply has
        # been sent. In other words, there is no serialization
        # guarantee unless the message transport mechanism is
        # synchronous between message and reply. This code is not
        # written to expect that feature, so it must deal with
        # out of order replies.
        if tracker.lastSentIndex  > message.maxIndex:
            # out of order, don't use this message
            # to continue catchup
            return
        tracker.matchIndex = message.maxIndex
        send_start_index = tracker.matchIndex + 1
        send_end_index = await self.log.get_last_index()
        # we want to send max of XXX, math is inclusive of both start and end
        if send_end_index - send_start_index > self.max_entries_per_message:
            send_end_index = send_start_index + self.max_entries_per_message
        tracker.nextIndex = send_end_index + 1
        tracker.lastSentIndex = send_end_index
        entries = []
        for index in range(send_start_index, send_end_index + 1):
            rec = await self.log.read(index)
            # make sure the follower doesn't get confused about their local commit status
            rec.committed = False
            entries.append(rec)
        prevLogIndex = 0
        prevLogTerm = 0
        if send_start_index > 1:
            pre_rec = await self.log.read(send_start_index - 1)
            prevLogIndex = pre_rec.index
            prevLogTerm = pre_rec.term

        message = AppendEntriesMessage(sender=self.my_uri(),
                                       receiver=uri,
                                       term=await self.log.get_term(),
                                       entries=entries,
                                       prevLogTerm=prevLogTerm,
                                       prevLogIndex=prevLogIndex,
                                       commitIndex=await self.log.get_commit_index())
        self.logger.debug("sending catchup %s", message)
        await self.hull.record_substate(SubstateCode.sending_catchup)
        await self.record_sent_message(message)
        await self.hull.send_message(message)

    async def record_commit_checker(self, log_record):
        # count the followers that have committed this far
        ayes = 1  # for me
        for tracker in self.follower_trackers.values():
            if tracker.matchIndex >= log_record.index:
                ayes += 1
        if ayes > len(self.hull.get_cluster_node_ids()) / 2:
            if log_record.code == RecordCode.client_command:
                asyncio.create_task(self.run_command_locally(log_record))
            else:
                log_record.committed = True
                await self.log.replace(log_record)

    async def run_command_locally(self, log_record):
        # make a last check to ensure it is not already done
        log_rec = await self.log.read(log_record.index)
        if log_rec.committed:
            return
        result = None
        error_data = None
        await self.hull.record_substate(SubstateCode.local_command)
        try:
            self.logger.info("%s applying command committed at index %d", self.my_uri(),
                             await self.log.get_last_index())
            processor = self.hull.get_processor()
            result,error_data = await processor.process_command(log_record.command, log_record.serial)
        except Exception as e:
            error_data = traceback.format_exc()
        if error_data:
            self.logger.debug("%s running command produced error %s", self.my_uri(), error_data)
        else:
            log_rec.result = result
            log_rec.committed = True
            await self.log.replace(log_rec)
        waiter = self.command_waiters[log_rec.index]
        if waiter:
            await waiter.handle_run_result(result, error_data)

    async def term_expired(self, message):
        await self.log.set_term(message.term)
        await self.hull.demote_and_handle(message)
        return None

    async def record_sent_message(self, message):
        tracker = await self.tracker_for_follower(message.sender)
        tracker.msg_count += 1
        tracker.last_msg_time = time.time()

    async def record_received_message(self, message):
        tracker = await self.tracker_for_follower(message.sender)
        tracker.reply_count += 1
        tracker.last_reply_time = time.time()
                                
    async def tracker_for_follower(self, uri):
        tracker = self.follower_trackers.get(uri, None)
        last_index = await self.log.get_last_index()
        if not tracker:
            tracker = FollowerTracker(uri=uri,
                                      nextIndex=last_index + 1,
                                      matchIndex=0)
            self.follower_trackers[uri] = tracker
        return tracker
        

