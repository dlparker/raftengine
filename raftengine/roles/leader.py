import logging 
import asyncio
import time
import json
import traceback
from dataclasses import dataclass
from typing import Dict, List, Any
from enum import Enum
from raftengine.api.types import RoleName, OpDetail, ClusterConfig
from raftengine.api.log_api import LogRec, RecordCode
from raftengine.api.hull_api import CommandResult
from raftengine.messages.append_entries import AppendEntriesMessage,AppendResponseMessage
from raftengine.messages.power import TransferPowerMessage, TransferPowerResponseMessage
from raftengine.messages.snapshot import SnapShotMessage
from raftengine.messages.cluster_change import ChangeOp
from raftengine.messages.base_message import BaseMessage
from raftengine.roles.base_role import BaseRole
from raftengine.hull.cluster_ops import SnapShotCursor

class TimeoutTaskGroup(Exception):
    """Exception raised to terminate a task group due to timeout."""


class Leader(BaseRole):

    def __init__(self, hull, cluster_ops, term, use_check_quorum):
        super().__init__(hull, RoleName.leader, cluster_ops)
        self.last_broadcast_time = 0
        self.logger = logging.getLogger("Leader")
        self.command_waiters = dict()
        self.bcast_pendings = []
        self.use_check_quorum = use_check_quorum
        self.accepting_commands = True
        self.exit_in_progress = False
        self.transfer_in_progress = False

    async def max_entries_per_message(self):
        return await self.cluster_ops.get_max_entries_per_message()
        
    async def start(self):
        await super().start()
        for uri in self.cluster_ops.get_cluster_node_ids():
            tracker = await self.cluster_ops.tracker_for_follower(uri)
        await self.run_after(await self.cluster_ops.get_heartbeat_period(), self.scheduled_send_heartbeats)
        start_record = LogRec(code=RecordCode.term_start,
                              term=await self.log.get_term(),
                              command=await self.cluster_ops.get_cluster_config_json_string(),
                              leader_id=self.my_uri())
        the_record = await self.log.append(start_record)
        self.logger.info("New Leader %s senting term start record index %d %d %d", self.my_uri(),
                         the_record.index, await self.log.get_last_index(), await self.log.get_last_term())
        await self.broadcast_log_record(the_record)

    async def transfer_power(self, target_uri, log_record=None):
        if self.transfer_in_progress:
            return
        if target_uri not in self.cluster_ops.get_cluster_node_ids():
            raise Exception(f"{target_uri} is not in cluster node list")
        self.transfer_in_progress = True
        asyncio.get_event_loop().call_soon(lambda target_uri=target_uri, log_record=log_record:
                                         asyncio.create_task(self.transfer_runner(target_uri, log_record)))
        etime_min, etime_max = await self.cluster_ops.get_election_timeout_range()
        self.accepting_commands = False
        return time.time() + etime_max
        
    async def transfer_runner(self, target_uri, log_record):
        self.logger.info("%s checking readiness for power transfer to %s", self.my_uri(), target_uri)
        tracker = await self.cluster_ops.tracker_for_follower(target_uri)
        start_time = time.time()
        etime_min, etime_max = await self.cluster_ops.get_election_timeout_range()
        time_limit = time.time() + etime_max
        while tracker.matchIndex < await self.log.get_commit_index() and time.time() < time_limit:
            await self.send_heartbeats()
            last_pending = self.bcast_pendings[-1]
            while time.time() < time_limit:
                still_pending = False
                for msg in last_pending['messages']:
                    if msg.receiver == target_uri:
                        still_pending = True
                        break
                if not still_pending:
                    break
                await asyncio.sleep(0.001)
            await asyncio.sleep(0.01)
        if tracker.matchIndex < await self.log.get_commit_index():
            # we couldn't bring target up to date, have to give up
            self.logger.error("%s failed readiness check for power transfer to %s timeout", self.my_uri(), target_uri)
            self.accepting_commands = True
            self.transfer_in_progress = False
            return
        # now it is up to date, so we can proceed
        prevLogIndex, prevLogTerm = await self.get_prev_record_id(tracker.matchIndex + 1)
        term = await self.log.get_term()
        message = TransferPowerMessage(sender=self.my_uri(),
                                       receiver=target_uri,
                                       term=term,
                                       prevLogTerm=prevLogTerm,
                                       prevLogIndex=prevLogIndex)
        self.logger.info("%s sending transfer power to %s", self.my_uri(), target_uri)
        await self.hull.send_message(message)
        if log_record:
            # the fact that we got a log record means that we are supposed
            # to exit, but let's check a couple of things to validate that
            if log_record.code == RecordCode.cluster_config and self.exit_in_progress:
                asyncio.get_event_loop().call_later(0.01, lambda log_record=log_record:
                                         asyncio.create_task(self.delayed_exit(log_record)))
                return
        return

    async def get_prev_record_id(self, this_index):
        snap = await self.log.get_snapshot()
        if snap and this_index - 1 < snap.last_index + 1:
            if snap.last_index == this_index - 1:
                prevLogIndex = snap.last_index
                prevLogTerm = snap.last_term
            elif snap.last_index > this_index - 1:
                return None, None
        else:
            if this_index > 1:
                prev_rec = await self.log.read(this_index - 1)
                prevLogIndex = prev_rec.index
                prevLogTerm = prev_rec.term
            else:
                prevLogIndex = 0
                prevLogTerm = 0
        return prevLogIndex, prevLogTerm
                
        
    async def delayed_exit(self, log_record):
        await self.cluster_ops.finish_node_remove(self.my_uri())
        log_record.applied = True
        await self.log.replace(log_record)
        self.logger.info("%s leader exiting cluster", self.my_uri())
        await self.hull.note_exit_done(success=True)
        
    async def run_command(self, command, timeout=1.0, serial=None):
        if not self.accepting_commands:
            return CommandResult(command=command,retry=True)
        # first save it in the log
        if serial is None:
            serial = await self.log.get_last_index() + 1
        raw_rec = LogRec(command=command, term=await self.log.get_term(),
                         leader_id=self.my_uri(), serial=serial)
        log_rec = await self.log.append(raw_rec)
        self.logger.debug("%s saved log record at index %d", self.my_uri(), log_rec.index)
        # now send it to everybody
        await self.broadcast_log_record(log_rec)
        waiter = CommandWaiter(self, log=self.log, orig_log_record=log_rec, timeout=timeout)
        self.command_waiters[log_rec.index] = waiter
        self.logger.info("%s waiting for completion of pending command", self.my_uri())
        result = await waiter.wait_for_result()
        return result

    async def broadcast_log_record(self, log_record):
        prevLogIndex, prevLogTerm = await self.get_prev_record_id(log_record.index)
        term = await self.log.get_term()
        commit_index = await self.log.get_commit_index()
        proto_message = AppendEntriesMessage(sender=self.my_uri(),
                                             receiver='',
                                             term=term,
                                             entries=[log_record,],
                                             prevLogTerm=prevLogTerm,
                                             prevLogIndex=prevLogIndex,
                                             commitIndex=commit_index)
        if log_record.code == RecordCode.term_start:
            await self.hull.record_op_detail(OpDetail.broadcasting_term_start)
        msgs = []
        for uri in self.cluster_ops.get_cluster_node_ids():
            if uri == self.my_uri():
                continue
            tracker = await self.cluster_ops.tracker_for_follower(uri)
            if tracker.nextIndex < log_record.index:
                # we don't send the new record unless the
                # follower is up to date, it will get
                # a copy once it gets caught up
                self.logger.debug("%s not sending to %s, it ti %d < li %d", self.my_uri(), uri, tracker.nextIndex, log_record.index)
                continue
            message = AppendEntriesMessage.from_dict(proto_message.__dict__)
            message.receiver = uri
            self.logger.info("broadcast command sending %s", message)
            await self.hull.send_message(message)
            msgs.append(message)
            await self.record_sent_message(message)
        self.bcast_pendings.append(dict(time=time.time(), messages=msgs, sent_count=len(msgs)))
        self.logger.debug("%s pending broadcast records %d", self.my_uri(), len(self.bcast_pendings))
        
    async def scheduled_send_heartbeats(self):
        await self.send_heartbeats()
        await self.run_after(await self.cluster_ops.get_heartbeat_period(), self.scheduled_send_heartbeats)

    async def send_heartbeats(self, target_only=None):
        entries = []
        if self.use_check_quorum and len(self.bcast_pendings) > 0:
            if not await self.check_quorum():
                return
        term = await self.log.get_term()
        my_uri = self.my_uri()
        last_term = await self.log.get_last_term()
        last_index = await self.log.get_last_index()
        commit_index = await self.log.get_commit_index()
        msgs = []
        if target_only:
            nodes = [target_only,]
        else:
            nodes = self.cluster_ops.get_cluster_node_ids() 
        for uri in nodes:
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
            msgs.append(message)
        self.bcast_pendings.append(dict(time=time.time(), messages=msgs, sent_count=len(msgs)))
        self.logger.debug("%s pending broadcast records %d", self.my_uri(), len(self.bcast_pendings))
        
    async def on_append_entries_response(self, message):
        tracker = await self.cluster_ops.tracker_for_follower(message.sender)
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
        tracker.matchIndex = message.maxIndex
        if message.maxIndex == tracker.nextIndex:
            tracker.nextIndex += 1
            self.logger.debug('Success to %s upped tracker.nextIndex to %d',
                              message.sender, tracker.nextIndex)
        if tracker.add_loading:
            self.logger.debug("%s node %s pre cluster join load progress at %d", self.my_uri(),
                              message.sender, message.maxIndex)
            if not await self.cluster_ops.note_loading_progress(message.sender, message.maxIndex, self):
                # false result means loading was aborted, done process this message any further
                return
        if tracker.nextIndex > await self.log.get_last_index():
            self.logger.debug('After success to %s tracker.nextIndex = %d tracker.matchIndex = %d',
                              message.sender, tracker.nextIndex, tracker.matchIndex)
            if (tracker.matchIndex > await self.log.get_commit_index()
                or tracker.matchIndex > await self.log.get_applied_index()):
                # see if this message completes the majority saved requirement
                # that defines commit at the cluster level, and apply it
                # if so.
                snap = await self.log.get_snapshot()
                if not snap or snap.last_index < tracker.matchIndex:
                    log_rec = await self.log.read(tracker.matchIndex)
                    await self.record_commit_checker(log_rec)
            if tracker.matchIndex == await self.log.get_last_index():
                return

        await self.send_catchup(message)
        self.logger.debug('After catchup %s tracker.nextIndex = %d tracker.matchIndex = %d',
                          message.sender, tracker.nextIndex, tracker.matchIndex)
        
    async def send_backdown(self, message):
        uri = message.sender
        tracker = await self.cluster_ops.tracker_for_follower(uri)
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
        prevLogIndex, prevLogTerm = await self.get_prev_record_id(send_index)
        if prevLogIndex is None:
            # we must have a snapshot, so check
            snap = await self.log.get_snapshot()
            if snap and snap.last_index >= send_index:
                # start the snapshot send process for this node
                await self.start_snapshot_send(uri)
                return
        rec = await self.log.read(send_index)
        rec.committed = False
        rec.applied = False
        entries = [rec,]
        message = AppendEntriesMessage(sender=self.my_uri(),
                                       receiver=uri,
                                       term=await self.log.get_term(),
                                       entries=entries,
                                       prevLogTerm=prevLogTerm,
                                       prevLogIndex=prevLogIndex,
                                       commitIndex=await self.log.get_commit_index())
        self.logger.info("sending backdown %s", message)
        await self.hull.record_op_detail(OpDetail.sending_backdown)
        await self.record_sent_message(message)
        await self.hull.send_message(message)
    
    async def send_catchup(self, message):
        uri = message.sender
        tracker = await self.cluster_ops.tracker_for_follower(uri)
        tracker.matchIndex = message.maxIndex
        send_start_index = tracker.matchIndex + 1
        send_end_index = await self.log.get_last_index()
        # we want to send max of XXX, math is inclusive of both start and end
        max_e = await self.max_entries_per_message()
        if send_end_index - send_start_index > max_e:
            send_end_index = send_start_index + max_e
        tracker.nextIndex = send_end_index + 1
        entries = []
        for index in range(send_start_index, send_end_index + 1):
            rec = await self.log.read(index)
            # make sure the follower doesn't get confused about their local commit status
            rec.committed = False
            entries.append(rec)
        prevLogIndex, prevLogTerm = await self.get_prev_record_id(send_start_index)
        message = AppendEntriesMessage(sender=self.my_uri(),
                                       receiver=uri,
                                       term=await self.log.get_term(),
                                       entries=entries,
                                       prevLogTerm=prevLogTerm,
                                       prevLogIndex=prevLogIndex,
                                       commitIndex=await self.log.get_commit_index())
        self.logger.debug("sending catchup %s", message)
        await self.hull.record_op_detail(OpDetail.sending_catchup)
        await self.record_sent_message(message)
        await self.hull.send_message(message)

    async def record_commit_checker(self, log_record):
        # count the followers that have committed this far
        ayes = 0
        if not self.exit_in_progress:
            ayes += 1  # for me
        for tracker in self.cluster_ops.get_all_follower_trackers():
            # don't count new node that is in process of loading, not yet
            # added to cluster
            if tracker.matchIndex >= log_record.index and not tracker.add_loading:
                ayes += 1
        if ayes > len(self.cluster_ops.get_cluster_node_ids()) / 2:
            # update the log record, just in case
            rec = await self.log.read(log_record.index)
            # We might be hear because the record is committed but
            # not applied, but saving the commit state anyway
            # is harmless and simplifies the code. It is
            # an extra log write, but it is a very rare event.
            rec.committed = True
            await self.log.replace(rec)
            if rec.code == RecordCode.client_command:
                asyncio.create_task(self.run_command_locally(rec))
            elif rec.code == RecordCode.cluster_config and not rec.applied:
                await self.cluster_ops.cluster_config_vote_passed(rec, self)

    async def run_command_locally(self, log_record):
        # make a last check to ensure it is not already done
        log_rec = await self.log.read(log_record.index)
        if log_rec.applied:
            return
        result = None
        error_data = None
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
            log_rec.applied = True
            await self.log.replace(log_rec)
            self.logger.debug("%s running command produced no error, apply_index is now %s", self.my_uri(), await self.log.get_applied_index())
        waiter = self.command_waiters[log_rec.index]
        if waiter:
            await waiter.handle_run_result(result, error_data)

    async def start_snapshot_send(self, target_uri):
        tracker = await self.cluster_ops.tracker_for_follower(target_uri)
        snap = await self.hull.pilot.begin_snapshot_export(await self.log.get_snapshot())
        cursor = SnapShotCursor(target_uri, snap, 0, False)
        tracker.sending_snapshot = cursor
        await self.snapshot_send(target_uri)
        
    async def snapshot_send(self, target_uri):
        tracker = await self.cluster_ops.tracker_for_follower(target_uri)
        ref = tracker.sending_snapshot
        snap = ref.snapshot
        tool = snap.tool
        chunk, new_offset, done = await tool.get_snapshot_chunk(ref.offset)
        message = SnapShotMessage(sender=self.my_uri(),
                                   receiver=target_uri,
                                   term=await self.log.get_term(),
                                   prevLogIndex=snap.last_index,
                                   prevLogTerm=snap.last_term,
                                   leaderId=self.my_uri(),
                                   offset=ref.offset,
                                   done=done,
                                   data=chunk)
        if ref.offset == 0:
            message.clusterConfig = await self.cluster_ops.get_cluster_config_json_string()
        ref.offset = new_offset
        ref.done = done
        await self.hull.send_message(message)

        
    async def on_snapshot_response_message(self, message):
        tracker = await self.cluster_ops.tracker_for_follower(message.sender)
        if tracker.sending_snapshot:
            snap = tracker.sending_snapshot.snapshot
            if tracker.sending_snapshot.done and message.success:
                tracker.sending_snapshot = None
                tracker.nextIndex = snap.last_index + 1
                tracker.matchIndex = snap.last_index 
                await self.send_heartbeats(target_only=message.sender)
                return
        await self.snapshot_send(message.sender)
        
    async def term_expired(self, message):
        await self.hull.set_term(message.term)
        await self.hull.demote_and_handle(message)
        return None

    async def record_sent_message(self, message):
        tracker = await self.cluster_ops.tracker_for_follower(message.sender)
        tracker.msg_count += 1
        tracker.last_msg_time = time.time()

    async def record_received_message(self, message):
        tracker = await self.cluster_ops.tracker_for_follower(message.sender)
        tracker.reply_count += 1
        tracker.last_reply_time = time.time()
        pop_bcasts = []
        for b_index, pending in enumerate(self.bcast_pendings):
            targ = None
            for m_index, msg in enumerate(pending['messages']):
                if message.is_reply_to(msg):
                    targ = m_index
                    break
            if targ is not None:
                pending['messages'].pop(targ)
                self.logger.debug("%s found reply to pending broadcast records %d from %s %d left", self.my_uri(),
                                  b_index, message.sender, len(pending['messages']))
                if len(pending['messages']) == 0:
                    pop_bcasts.append(pending)

        for pop_b in pop_bcasts:
            self.bcast_pendings.remove(pop_b)
        self.logger.debug("%s after in message pending broadcast records %d", self.my_uri(), len(self.bcast_pendings))
                
    async def check_quorum(self):
        et_min, et_max = await self.cluster_ops.get_election_timeout_range()
        pop_bcasts = []
        for b_index,pending in enumerate(self.bcast_pendings):
            reply_count = pending['sent_count'] - len(pending['messages']) 
            quorum = int(pending['sent_count']/2) # normal cluster is odd, yielding x.5 rounds up to x + 1, which works
            if reply_count >= quorum:
                pop_bcasts.append(pending)
            elif time.time() - pending['time'] > et_max:
                self.logger.warning("%s failed quorum check, resigning ", self.my_uri())
                await self.hull.demote_and_handle()
                return False
        for p_b in pop_bcasts:
            self.bcast_pendings.remove(p_b)
        return True
        
    async def on_membership_change_message(self, message):
        last = await self.log.get_last_index()
        await self.cluster_ops.do_node_inout(message.op, message.target_uri, self, message)

    async def do_node_exit(self, target_uri):
        return await self.cluster_ops.do_node_inout("REMOVE", target_uri, self)
    
    
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
            if self.leader.hull.role != self.leader:
                self.leader.logger.debug("%s after timeout exception and am no longer leader! maybe %s?",
                                         self.leader.my_uri(), self.leader.hull.leader_uri)
                self.result = CommandResult(command=self.orig_log_record.command,
                                            committed=False,
                                            redirect=self.leader.hull.leader_uri)
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
            await self.leader.hull.event_control.emit_error(error_data)
        else:
            log_record = await self.log.read(self.orig_log_record.index)
            log_record.result = command_result
            new_rec = await self.log.replace(log_record)
        self.result = result
        async with self.done_condition:
            self.done_condition.notify()
        return 
        
