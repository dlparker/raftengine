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

        
@dataclass
class FollowerTracker:
    uri: str 
    nextIndex: int = 0
    matchIndex: int = 0
    msg_count: int = 0
    reply_count: int = 0
    last_msg_time: int = 0
    last_reply_time: int = 0


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
                    with self.done_condition:
                        self.done_condition.notify()
                return
            
        async def check_done():
            while not self.time_expired and not self.result:
                async with self.done_condition:
                    await self.done_condition.wait()
                    if self.time_expired:
                        self.result = CommandResult(command=self.log_record.command,
                                                    committed=False,
                                                    timeout=True,
                                                    result=None,
                                                    error=None,
                                                    redirect=None)
            return self.result
        
        async with asyncio.TaskGroup() as tg:
            tg.create_task(check_done())
            tg.create_task(do_timeout(self.timeout))
        return self.result

    async def handle_run_result(self, command_result, error_data):
        if not error_data:
            self.committed = True
        self.local_error = error_data
        result = CommandResult(command=self.orig_log_record.command,
                               committed=self.committed,
                               timeout=False,
                               result=command_result,
                               error=error_data,
                               redirect=None)
        if error_data:
            await self.leader.hull.record_substate(SubstateCode.failed_command)
        else:
            await self.leader.hull.record_substate(SubstateCode.committing_command)
            self.orig_log_record.local_committed = True
            self.orig_log_record.leader_committed = True
            new_rec = await self.log.replace(self.orig_log_record)
        self.result = result
        async with self.done_condition:
            self.done_condition.notify()
        return 
        
class Leader(BaseState):

    def __init__(self, hull, term):
        super().__init__(hull, StateCode.leader)
        self.last_broadcast_time = 0
        self.logger = logging.getLogger("Leader")
        self.follower_trackers = dict()
        self.command_waiters = dict()
                
    async def start(self):
        await super().start()
        last_index = await self.log.get_last_index()
        for uri in self.hull.get_cluster_node_ids():
            self.follower_trackers[uri] = FollowerTracker(uri=uri,
                                                          nextIndex=last_index,
                                                          matchIndex=0)
        await self.run_after(self.hull.get_heartbeat_period(), self.send_heartbeats)
        await self.send_heartbeats()

    async def run_command(self, command, timeout=1.0):
        # first save it in the log
        raw_rec = LogRec(command=command, term=await self.log.get_term())
        log_rec = await self.log.append(raw_rec)
        # now send it to everybody
        await self.hull.record_substate(SubstateCode.broadcasting_command)
        await self.broadcast_log_record(log_rec)
        waiter = CommandWaiter(self, log=self.log, orig_log_record=log_rec, timeout=timeout)
        self.command_waiters[log_rec.index] = waiter
        self.logger.info("%s waiting for completion of pending command", self.my_uri())
        result = await waiter.wait_for_result()
        return result

    async def broadcast_log_record(self, log_record):
        await self.hull.record_substate(SubstateCode.preparing_command)
        term = await self.log.get_term()
        commit_index = await self.log.get_local_commit_index()
        proto_message = AppendEntriesMessage(sender=self.my_uri(),
                                             receiver='',
                                             term=term,
                                             entries=[log_record,],
                                             prevLogTerm=await self.log.get_last_term(),
                                             prevLogIndex=await self.log.get_last_index(),
                                             commitIndex=commit_index)
        await self.hull.record_substate(SubstateCode.broadcasting_command)
        for uri in self.hull.get_cluster_node_ids():
            if uri == self.my_uri():
                continue
            message = AppendEntriesMessage.from_dict(proto_message.__dict__)
            message.receiver = uri
            message.encode_entries()
            self.logger.info("sending %s", message)
            await self.hull.send_message(message)
            await self.record_sent_message(message)

    async def send_heartbeats(self):
        silent_time = time.time() - self.last_broadcast_time
        remaining_time = self.hull.get_heartbeat_period() - silent_time
        if  remaining_time > 0:
            self.logger.debug("%s resched heartbeats time left %f", self.my_uri, remaining_time)
            await self.run_after(remaining_time, self.send_heartbeats)
            return
        entries = json.dumps([])
        term = await self.log.get_term()
        my_uri = self.my_uri()
        last_term = await self.log.get_last_term()
        last_index = await self.log.get_last_index()
        commit_index = await self.log.get_local_commit_index()
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
            self.logger.debug("%s sending heartbeat to %s", message.sender, message.receiver)
            await self.hull.send_message(message)
            await self.record_sent_message(message)
            self.last_broadcast_time = time.time()
        
    async def on_append_entries_response(self, message):
        await self.record_received_message(message)
        if message.recordIds != []:
            # follower saved new records, so maybe we need to commit something
            for rec_id in message.recordIds:
                log_rec = await self.log.read(rec_id)
                if log_rec.local_committed:
                    continue
                await self.command_commit_checker(log_rec)
        if message.prevLogIndex < await self.log.get_last_index():
            await self.catch_follower_up(message)
            return

    async def catch_follower_up(self, message):
        # get the first log record they are missing, send that one
        follower_last_index = message.prevLogIndex
        follower_last_term = message.prevLogTerm

        entries = []
        max_index = await self.log.get_last_index()
        start_index = follower_last_index + 1
        if max_index - start_index > 10:
            max_index = start_index + 10
        for index in range(start_index, max_index + 1):
            entries.append(await self.log.read(index))
        # not sure why the doc says I need this, follower always tells us.
        tracker = self.follower_trackers[message.sender]
        tracker.matchIndex = message.prevLogIndex
        tracker.nextIndex = max_index + 1
        message = AppendEntriesMessage(sender=self.my_uri(),
                                       receiver=message.sender,
                                       term=await self.log.get_term(),
                                       entries=entries,
                                       prevLogTerm=await self.log.get_term(),
                                       prevLogIndex=await self.log.get_last_index(),
                                       commitIndex=await self.log.get_local_commit_index())
        message.encode_entries()
        self.logger.info("sending catchup %s", message)
        await self.hull.record_substate(SubstateCode.sending_catchup)
        await self.record_sent_message(message)
        await self.hull.send_message(message)
        
    async def command_commit_checker(self, log_record):
        # count the followers that have committed this far
        ayes = 1  # for me
        for tracker in self.follower_trackers.values():
            if tracker.matchIndex >= log_record.index:
                ayes += 1
        if ayes > len(self.hull.get_cluster_node_ids()) / 2:
            asyncio.create_task(self.run_command_locally(log_record))

    async def run_command_locally(self, log_record):
        # make a last check to ensure it is not already done
        log_rec = await self.log.read(log_record.index)
        if log_rec.local_committed:
            if not log_rec.leader_committed:
                log_rec.leader_committed = True
                await self.log.replace(log_rec.index)
            return
        result = None
        error_data = None
        await self.hull.record_substate(SubstateCode.local_command)
        try:
            self.logger.info("%s applying command committed at index %d", self.my_uri(),
                             await self.log.get_last_index())
            processor = self.hull.get_processor()
            result,error_data = await processor.process_command(log_record.command)
        except Exception as e:
            error_data = traceback.format_exc()
        if error_data:
            self.logger.debug("%s running command produced error %s", self.my_uri(), error_data)
        else:
            log_rec.result = result
            log_rec.local_committed = True
            log_rec.leader_committed = True
            await self.log.replace(log_rec)
        waiter = self.command_waiters[log_rec.index]
        if waiter:
            await waiter.handle_run_result(result, error_data)

    async def term_expired(self, message):
        await self.log.set_term(message.term)
        await self.hull.demote_and_handle()
        return message

    async def record_sent_message(self, message):
        tracker = self.follower_trackers[message.receiver]
        tracker.msg_count += 1
        tracker.last_msg_time = time.time()

    async def record_received_message(self, message):
        tracker = self.follower_trackers.get(message.sender, None)
        if not tracker:
            # not sure how this could happen, config should update before hearing from
            # new follower, but let's code defensively
            tracker = FollowerTracker(uri=message.sender,
                                      nextIndex=0,
                                      matchIndex=0)
            self.follower_trackers[message.sender] = tracker
        tracker.reply_count += 1
        tracker.last_reply_time = time.time()
        tracker.matchIndex = message.prevLogIndex
                                



