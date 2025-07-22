import logging 
import asyncio
import time
import json
import math
import traceback
from dataclasses import dataclass, field
from collections import defaultdict
from typing import Dict, List, Any
from enum import Enum
from raftengine.api.types import RoleName, OpDetail, ClusterConfig
from raftengine.api.log_api import LogRec, RecordCode
from raftengine.api.deck_api import CommandResult
from raftengine.messages.append_entries import AppendEntriesMessage,AppendResponseMessage
from raftengine.messages.power import TransferPowerMessage, TransferPowerResponseMessage
from raftengine.messages.snapshot import SnapShotMessage
from raftengine.messages.cluster_change import ChangeOp
from raftengine.messages.base_message import BaseMessage
from raftengine.messages.message_codec import SerialNumberGenerator
from raftengine.roles.base_role import BaseRole
from raftengine.deck.cluster_ops import SnapShotCursor

class TimeoutTaskGroup(Exception):
    """Exception raised to terminate a task group due to timeout."""

@dataclass
class MessageTracker:
    uri:str
    message: AppendEntriesMessage
    broadcast_id: int = field(default=None)
    sent_time: float = field(default_factory=time.time)
    log_rec_ids: list = field(default_factory=list) # if empty list, is heartbeat
    reply: AppendResponseMessage = None
    reply_time: float = None
    
@dataclass
class BroadcastTracker: # broadcasts never have more than one log record
    id: int  
    followers: dict[str, MessageTracker] = field(default_factory=dict)
    sent_time: float = field(default_factory=time.time)
    reply_count: int = 0   # this counts replies regardless of success flag, follower responded with something
    approve_count: int = 0 # must reach quroum to commit log records in message
    
@dataclass
class LogVoteTracker:
    log_index: int
    voters: list[str] = field(default_factory=list)
    votes: dict[str, bool] = field(default_factory=dict)
    
@dataclass
class CommandTracker:
    serial: int
    command: str
    rep_rec: BroadcastTracker
    result: str = None
    error_data: str = None
    future: asyncio.Future = None
    
class Leader(BaseRole):

    def __init__(self, deck, cluster_ops, term, use_check_quorum):
        super().__init__(deck, RoleName.leader, cluster_ops)
        self.last_broadcast_time = 0
        self.logger = logging.getLogger("Leader")
        #self.bcast_pendings = []
        self.active_commands = {}
        self.command_condition = asyncio.Condition()
        self.active_commands_lock = asyncio.Lock() 
        self.use_check_quorum = use_check_quorum
        self.accepting_commands = True
        self.exit_in_progress = False
        self.transfer_in_progress = False
        self.active_messages = defaultdict(dict) # indexed by target uri, contains dict of MessageTrackers
        self.broadcast_id = 0
        self.broadcast_trackers = {} # indexed by self.broadcast_id, incr
        self.log_vote_trackers = {} # indexed by log id
        self.command_error_strategy = "idempotent" # primitive, transactional, retryable

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
        bcast_tracker = BroadcastTracker(self.broadcast_id, followers={})
        self.broadcast_trackers[self.broadcast_id] = bcast_tracker
        self.broadcast_id += 1
        node_uris = self.cluster_ops.get_cluster_node_ids()
        votes = {self.my_uri() :True}
        lvt = LogVoteTracker(log_record.index, voters=node_uris, votes=votes)
        self.log_vote_trackers[log_record.index] = lvt
        if log_record.code == RecordCode.term_start:
            await self.deck.record_op_detail(OpDetail.broadcasting_term_start)
        msgs = []
        for uri in node_uris:
            if uri == self.my_uri():
                continue
            tracker = await self.cluster_ops.tracker_for_follower(uri)
            message = AppendEntriesMessage.from_dict(proto_message.__dict__)
            message.receiver = uri
            message.serial_number = SerialNumberGenerator.get_generator().generate()
            msg_tracker = MessageTracker(uri, message=message, log_rec_ids=[log_record.index,])
            self.active_messages[uri][message.serial_number] = msg_tracker
            self.logger.debug("sending log_rec %s, active for %s %d", message, uri,
                          len(self.active_messages[uri]))
            bcast_tracker.followers[uri] = msg_tracker
            msg_tracker.broadcast_id = bcast_tracker.id
            await self.deck.send_message(message)
            msgs.append(message)
            asyncio.create_task(self.record_sent_message(message))
        
    async def scheduled_send_heartbeats(self):
        await self.send_heartbeats()
        await self.run_after(await self.cluster_ops.get_heartbeat_period(), self.scheduled_send_heartbeats)

    async def send_heartbeats(self, target_only=None):
        entries = []
        if self.use_check_quorum and False:
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
            bcast_tracker = BroadcastTracker(self.broadcast_id, followers=dict())
            self.broadcast_trackers[self.broadcast_id] = bcast_tracker
            self.broadcast_id += 1            
        for uri in nodes:
            if uri == self.my_uri():
                continue
            serial_number = SerialNumberGenerator.get_generator().generate()
            message = AppendEntriesMessage(sender=my_uri,
                                           receiver=uri,
                                           term=term,
                                           serial_number=serial_number,
                                           entries=entries,
                                           prevLogTerm=last_term,
                                           prevLogIndex=last_index,
                                           commitIndex=commit_index)
            msg_tracker = MessageTracker(uri, message)
            self.active_messages[uri][serial_number] = msg_tracker
            if target_only:
                self.logger.debug("sending append_entries to %s, active for %s %d", message, uri,
                                  len(self.active_messages[uri]))
            else:
                self.logger.debug("sending heartbeat %s, active for %s %d", message, uri,
                                  len(self.active_messages[uri]))
                bcast_tracker.followers[uri] = msg_tracker
                msg_tracker.broadcast_id = bcast_tracker.id
            await self.record_sent_message(message)
            self.last_broadcast_time = time.time()
            msgs.append(message)
            await self.deck.send_message(message)

    async def ensure_log_tracker(self, log_record):
        vote_tracker = self.log_vote_trackers.get(log_record.index, None)
        if vote_tracker is not None:
            return vote_tracker
        # need to see if other nodes are already past this
        # record and setup a vote tracker accordingly
        node_uris = self.cluster_ops.get_cluster_node_ids()
        node_uris = self.cluster_ops.get_cluster_node_ids()
        votes = {self.my_uri() :True}
        vote_tracker = LogVoteTracker(log_record.index, voters=node_uris, votes=votes)
        for uri in node_uris:
            if uri != self.my_uri():
                node_tracker = await self.cluster_ops.tracker_for_follower(url)
                if node_tracker.maxIndex >= log_record.index:
                    # this node has already voted true at some point, maybe
                    # before crash or change of leadership
                    vote_tracker.votes[uri] = True
        self.log_vote_trackers[log_record.index] = vote_tracker
        return vote_tracker
        
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
            if snap and snap.index >= send_index:
                # start the snapshot send process for this node
                await self.start_snapshot_send(uri)
                return
        rec = await self.log.read(send_index)
        entries = [rec,]
        rec_ids = [rec.index,]
        if not rec.committed:
            await self.ensure_log_tracker(rec)
        serial_number = SerialNumberGenerator.get_generator().generate()
        message = AppendEntriesMessage(sender=self.my_uri(),
                                       receiver=uri,
                                       term=await self.log.get_term(),
                                       serial_number=serial_number,
                                       entries=entries,
                                       prevLogTerm=prevLogTerm,
                                       prevLogIndex=prevLogIndex,
                                       commitIndex=await self.log.get_commit_index())
        self.active_messages[uri][serial_number] = MessageTracker(uri, message, log_rec_ids=rec_ids)
        self.logger.debug("sending backdown %s, active for %s %d", message, uri,
                          len(self.active_messages[uri]))
        await self.deck.record_op_detail(OpDetail.sending_backdown)
        await self.record_sent_message(message)
        await self.deck.send_message(message)
    
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
        ids = []
        for index in range(send_start_index, send_end_index + 1):
            rec = await self.log.read(index)
            entries.append(rec)
            ids.append(rec.index)
            if not rec.committed:
                await self.ensure_log_tracker(rec)
        prevLogIndex, prevLogTerm = await self.get_prev_record_id(send_start_index)
        serial_number = SerialNumberGenerator.get_generator().generate()
        message = AppendEntriesMessage(sender=self.my_uri(),
                                       receiver=uri,
                                       term=await self.log.get_term(),
                                       serial_number=serial_number,
                                       entries=entries,
                                       prevLogTerm=prevLogTerm,
                                       prevLogIndex=prevLogIndex,
                                       commitIndex=await self.log.get_commit_index())
        self.active_messages[uri][serial_number] = MessageTracker(uri, message, log_rec_ids=ids)
        self.logger.debug("sending catchup %s, active for %s %d", message, uri,
                          len(self.active_messages[uri]))
        await self.deck.record_op_detail(OpDetail.sending_catchup)
        await self.record_sent_message(message)
        await self.deck.send_message(message)

    async def on_append_entries_response(self, message):
        node_tracker = await self.cluster_ops.tracker_for_follower(message.sender)
        self.logger.debug('handling response %s', message)
        self.logger.debug('follower=%s at message beginning tracker.nextIndex = %d tracker.matchIndex = %d',
                          message.sender, node_tracker.nextIndex, node_tracker.matchIndex)
        # regardless of the message situation or success flag, record what the follower
        # say it has as last index in log
        node_tracker.matchIndex = message.maxIndex
        # tracker.nextIndex is our local belief about which
        # log record the follower needs next. It may be higher
        # than the matchIndex if multiple log record appends
        # are in flight, which is common under load.
        # If they are eqaual, then follower has caught up
        # so we update the index we think it needs next. This
        # may or may not be past the end of our local log. Don't care.
        if node_tracker.matchIndex == node_tracker.nextIndex:
            node_tracker.nextIndex += 1
        msg_tracker = self.active_messages[message.sender].get(message.original_serial, None)
        if msg_tracker is None:
            # don't know how this could happen, the message and reply would have to span a restart
            # of the leader, and that doesn't make sense
            raise Exception(f'No record of append_entries matching reply from {message.sender}')
        msg_tracker.reply = message
        del self.active_messages[message.sender][message.original_serial]
        self.logger.debug("procesing %s, active for %s %d", message, message.sender,
                          len(self.active_messages[message.sender]))
        # the message may have been a heartbeat, or a broadcast,
        # or a backdown/catchup message that included log records
        # broadcast earlier.
        bcast_tracker = None
        if not msg_tracker.broadcast_id:
            # not a broadcast message, must backdown or catchup
            if message.success:
                # see if follower caught up
                local_last = await self.log.get_last_index()
                if message.maxIndex == local_last:
                    self.logger.debug('Follower %s  caught up: node_tracker.nextIndex = %d node_tracker.matchIndex = %d',
                                  message.sender, node_tracker.nextIndex, node_tracker.matchIndex)
                    return
                # not caught up, try some more log records
                await self.send_catchup(message)
                self.logger.debug('After catchup to %s node_tracker.nextIndex = %d node_tracker.matchIndex = %d',
                                  message.sender, node_tracker.nextIndex, node_tracker.matchIndex)
                return
            else:
                # follower said no log match, needs backdown
                await self.send_backdown(message)
                self.logger.debug('After backdown to %s node_tracker.nextIndex = %d node_tracker.matchIndex = %d',
                                  message.sender, node_tracker.nextIndex, node_tracker.matchIndex)
                return
        # Message was part of a broadcast, so see what needs to be done
        # with that
        bcast_tracker = self.broadcast_trackers[msg_tracker.broadcast_id]
        bcast_tracker.reply_count += 1
        if bcast_tracker.reply_count == len(bcast_tracker.followers):
            self.logger.debug("Broadcast reply from %s last expected", message.sender)
            del self.broadcast_trackers[msg_tracker.broadcast_id]
        if len(msg_tracker.log_rec_ids) == 0:
            self.logger.debug("Heartbeat response from %s", message.sender)
            if not message.success:
                # follower said heartbeat no good, needs backdown
                self.logger.debug("Heartbeat response from %s no joy, needs backdown", message.sender)
                await self.send_backdown(message)
                self.logger.debug('After backdown to %s node_tracker.nextIndex = %d node_tracker.matchIndex = %d',
                                  message.sender, node_tracker.nextIndex, node_tracker.matchIndex)
            return
        await self.assess_log_vote(msg_tracker)
        local_last = await self.log.get_last_index()
        if message.maxIndex < local_last:
            await self.send_catchup(message)
            self.logger.debug('After catchup to %s node_tracker.nextIndex = %d node_tracker.matchIndex = %d',
                              message.sender, node_tracker.nextIndex, node_tracker.matchIndex)
        return

    async def assess_log_vote(self, msg_tracker):
        reply = msg_tracker.reply
        trackers = []
        for entry in msg_tracker.message.entries:
            # there will be no vote tracker if the log record has already
            # been committed, means we are just getting node caught up, not voting
            lvt = self.log_vote_trackers.get(entry.index, None)
            if lvt:
                trackers.append(lvt)
        for vote_tracker in trackers:
            vote_tracker.votes[reply.sender] = reply.success
            node_count = len(vote_tracker.voters)
            if self.exit_in_progress:
                # if leader leaving, then it doesn't count itself in replication votes
                node_count -= 1
            win_count = math.ceil(node_count/2)
            if len(vote_tracker.votes) == len(vote_tracker.voters):
                del self.log_vote_trackers[entry.index]
            ayes = 0
            for uri in vote_tracker.voters:
                if self.exit_in_progress and uri == self.my_uri():
                    continue
                if vote_tracker.votes.get(uri, False):
                    ayes += 1
            if ayes >= win_count:
                self.logger.debug('Reply from %s completes commit quorum, doing commit', reply.sender)
                log_rec = await self.log.read(vote_tracker.log_index)
                if not log_rec.committed:
                    # this is explicit in the protocol, committing a record
                    # commits all prior records.
                    await self.commit_and_apply_before(log_rec.index)                    
                    log_rec.committed = True
                    await self.log.replace(log_rec)
                if not log_rec.applied:
                    # Pick up an records that have been committed but
                    # not applied, for whatever reason
                    await self.commit_and_apply_before(log_rec.index)                    
                    if log_rec.code == RecordCode.client_command:
                        self.logger.debug('Doing command apply')
                        asyncio.create_task(self.run_command_locally(log_rec))
                    elif log_rec.code == RecordCode.cluster_config:
                        self.logger.debug('Doing cluster ops config change vote passed logic')
                        await self.cluster_ops.cluster_config_vote_passed(log_rec, self)

    async def commit_and_apply_before(self, log_index):
        last_commit = await self.log.get_commit_index()
        if last_commit == 0:
            last_commit = 1
        if last_commit < log_index:
            for index in range(last_commit, log_index): # up to, not including
                rec = await self.log.read(index)
                rec.committed = True
                await self.log.replace(rec)
                if not rec.applied:
                    if rec.code == RecordCode.client_command:
                        self.logger.debug('Doing command apply')
                        asyncio.create_task(self.run_command_locally(rec))
                    elif rec.code == RecordCode.cluster_config:
                        self.logger.debug('Doing cluster ops config change vote passed logic')
                        await self.cluster_ops.cluster_config_vote_passed(log_rec, self)
            
        last_applied = await self.log.get_applied_index()
        if last_applied == 0:
            last_applied = 1
        if last_applied < log_index:
            for index in range(last_applied, log_index): # up to, not including
                rec = await self.log.read(index)
                if not rec.applied:
                    if rec.code == RecordCode.client_command:
                        self.logger.debug('Doing command apply')
                        asyncio.create_task(self.run_command_locally(rec))
                    elif rec.code == RecordCode.cluster_config:
                        self.logger.debug('Doing cluster ops config change vote passed logic')
                        await self.cluster_ops.cluster_config_vote_passed(log_rec, self)
            
    async def have_quorum(self, broadcast_tracker):
        return True
    
    async def run_command_locally(self, log_record):
        # make a last check to ensure it is not already done
        log_rec = await self.log.read(log_record.index)
        if log_rec.applied:
            return
        result = None
        error_data = None
        self.logger.info("%s applying command committed at index %d", self.my_uri(),
                         await self.log.get_last_index())
        processor = self.deck.get_processor()
        try:
            result,error_data = await processor.process_command(log_record.command, log_record.serial)
        except Exception as e:
            error_data = traceback.format_exc()
        if error_data:
            self.logger.debug("%s running command produced error %s", self.my_uri(), error_data)
            if self.command_error_strategy != "idempotent":
                log_rec.applied = True
                await self.log.replace(log_rec)
        else:
            self.logger.debug("%s running command produced no error, apply_index is now %s",
                              self.my_uri(), await self.log.get_applied_index())
            log_rec.applied = True
            await self.log.replace(log_rec)
        await self.report_command_result(log_rec, result, error_data)
        return

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
            self.logger.info("%s  %s matchIndex %d, should be %d", self.my_uri(),  target_uri,
                             tracker.matchIndex, await self.log.get_commit_index())
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
                await asyncio.sleep(0.0001)
            await asyncio.sleep(0.0001)
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
        await self.deck.send_message(message)
        if log_record:
            # the fact that we got a log record means that we are supposed
            # to exit, but let's check a couple of things to validate that
            if log_record.code == RecordCode.cluster_config and self.exit_in_progress:
                asyncio.get_event_loop().call_later(0.01, lambda log_record=log_record:
                                         asyncio.create_task(self.delayed_exit(log_record)))
                return
        self.logger.info("%s demoting and expecting %s as new leader", self.my_uri(), target_uri)
        await self.deck.demote_and_handle()
        return

    async def get_prev_record_id(self, this_index):
        snap = await self.log.get_snapshot()
        if snap and this_index - 1 < snap.index + 1:
            if snap.index == this_index - 1:
                prevLogIndex = snap.index
                prevLogTerm = snap.term
            elif snap.index > this_index - 1:
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
        await self.deck.note_exit_done(success=True)
        
    async def run_command(self, command, timeout=1.0):
        if not self.accepting_commands:
            return CommandResult(command=command, retry=True)
        serial = SerialNumberGenerator.get_generator().generate()
        raw_rec = LogRec(command=command, term=await self.log.get_term(),
                         leader_id=self.my_uri(), serial=serial)
        log_rec = await self.log.append(raw_rec)
        self.logger.debug("%s saved command serial %d log record at index %d", self.my_uri(),
                          serial, log_rec.index)
        async with self.active_commands_lock:
            self.active_commands[log_rec.index] = dict(serial=serial,
                                                       log_rec=log_rec,
                                                       result=None,
                                                       error_data=None,
                                                       yes_votes=0,
                                                       no_votes=0,
                                                       future=asyncio.Future())
        self.logger.info("%s waiting for completion of pending command %d", self.my_uri(), serial)
        command_result = await self.send_and_await_command(log_rec, timeout)
        
        self.logger.debug("%s command result sn=%d %s", self.my_uri(),
                          log_rec.serial,
                          f"(result_not_none={command_result.result is not None}" +
                          f", redirect={command_result.redirect}" +
                          f", error={command_result.error}" +
                          f", timeout_expired={command_result.timeout_expired})")

        return command_result


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


    async def start_snapshot_send(self, target_uri):
        tracker = await self.cluster_ops.tracker_for_follower(target_uri)
        snapshot = await self.log.get_snapshot()
        snapshot_tool = await self.deck.pilot.begin_snapshot_export(snapshot)
        cursor = SnapShotCursor(target_uri, snapshot, 0, False)
        tracker.sending_snapshot = cursor
        tracker.snapshot_tool = snapshot_tool
        await self.snapshot_send(target_uri)
        
    async def snapshot_send(self, target_uri):
        tracker = await self.cluster_ops.tracker_for_follower(target_uri)
        ref = tracker.sending_snapshot
        tool = tracker.snapshot_tool
        snap = ref.snapshot
        chunk, new_offset, done = await tool.get_snapshot_chunk(ref.offset)
        message = SnapShotMessage(sender=self.my_uri(),
                                   receiver=target_uri,
                                   term=await self.log.get_term(),
                                   prevLogIndex=snap.index,
                                   prevLogTerm=snap.term,
                                   leaderId=self.my_uri(),
                                   offset=ref.offset,
                                   done=done,
                                   data=chunk)
        if ref.offset == 0:
            message.clusterConfig = await self.cluster_ops.get_cluster_config_json_string()
        ref.offset = new_offset
        ref.done = done
        await self.deck.send_message(message)

        
    async def on_snapshot_response_message(self, message):
        tracker = await self.cluster_ops.tracker_for_follower(message.sender)
        if tracker.sending_snapshot:
            snap = tracker.sending_snapshot.snapshot
            if tracker.sending_snapshot.done and message.success:
                tracker.sending_snapshot = None
                tracker.snapshot_tool = None
                tracker.nextIndex = snap.index + 1
                tracker.matchIndex = snap.index 
                await self.send_heartbeats(target_only=message.sender)
                return
        await self.snapshot_send(message.sender)
        

    async def term_expired(self, message):
        await self.deck.set_term(message.term)
        await self.notify_pending_commands_on_demotion()
        await self.deck.demote_and_handle(message)
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
            for m_index, orig_msg in enumerate(pending['messages']):
                if message.is_reply_to(orig_msg):
                    targ = m_index
                    break
            if targ is not None:
                pending['messages'].pop(targ)
                self.logger.debug("%s found reply to pending broadcast records %d from %s %d left", self.my_uri(),
                                  b_index, message.sender, len(pending['messages']))
                if len(pending['messages']) == 0:
                    pop_bcasts.append(pending)
                #await vote_on_append(message, orig_msg)
        for pop_b in pop_bcasts:
            self.bcast_pendings.remove(pop_b)
        self.logger.debug("%s after in message pending broadcast records %d", self.my_uri(), len(self.bcast_pendings))
                

    async def check_quorum(self):
        et_min, et_max = await self.cluster_ops.get_election_timeout_range()
        pop_bcasts = []
        for b_index, pending in enumerate(self.bcast_pendings):
            reply_count = pending['sent_count'] - len(pending['messages'])
            quorum = int(pending['sent_count'] / 2) 
            if reply_count >= quorum:
                pop_bcasts.append(pending)
            elif time.time() - pending['time'] > et_max:
                self.logger.warning("%s failed quorum check, resigning", self.my_uri())
                await self.notify_pending_commands_on_demotion()
                await self.deck.demote_and_handle()
                return False
        for p_b in pop_bcasts:
            self.bcast_pendings.remove(p_b)
        return True
        
    async def on_membership_change_message(self, message):
        last = await self.log.get_last_index()
        await self.cluster_ops.do_node_inout(message.op, message.target_uri, self, message)

    async def do_node_exit(self, target_uri):
        return await self.cluster_ops.do_node_inout("REMOVE", target_uri, self)
    
    async def do_update_settings(self, settings):
        return await self.cluster_ops.do_update_settings(settings, self)
            
    async def send_and_await_command(self, log_rec, timeout=5.0):
        async with self.active_commands_lock:
            command_rec = self.active_commands[log_rec.index]
        self.logger.debug("%s broadcasting command serial %d for log index %d", self.my_uri(),
                         command_rec['serial'], log_rec.index)
        await self.broadcast_log_record(log_rec)
        start_time = time.time()
        remaining_wait = timeout
        while self.deck.role == self:
            try:
                result_data = await asyncio.wait_for(command_rec['future'], timeout=remaining_wait)
                async with self.active_commands_lock:
                    if log_rec.index in self.active_commands:
                        del self.active_commands[log_rec.index]
                result = CommandResult(
                    command=log_rec.command,
                    timeout_expired=False,
                    result=command_rec['result'],
                    error=command_rec['error_data'],
                    redirect=None
                )
                self.logger.debug("%s command result ready for serial %d for log index %d", self.my_uri(),
                         command_rec['serial'], log_rec.index)
                return result
            except asyncio.TimeoutError:
                remaining_wait = timeout - (time.time() - start_time)
                if remaining_wait <= 0:
                    self.logger.warning("%s command timeout for log index %d", self.my_uri(), log_rec.index)
                    async with self.active_commands_lock:
                        if log_rec.index in self.active_commands:
                            del self.active_commands[log_rec.index]
                    return CommandResult(
                        command=log_rec.command,
                        timeout_expired=True,
                        result=None,
                        error=None,
                        redirect=None
                    )
    async def report_command_result(self, log_rec, result, error_data):
        async with self.active_commands_lock:
            rec = self.active_commands.get(log_rec.index)
            if rec is None:
                self.logger.debug(
                    "%s command result for log index %d ignored, command not active",
                    self.my_uri(), log_rec.index
                )
                return
            rec['result'] = result
            rec['error_data'] = error_data
            rec['future'].set_result(True)
            self.logger.debug(
                "%s reported command result for log index %d, error: %s",
                self.my_uri(), log_rec.index, error_data
            )

    async def notify_pending_commands_on_demotion(self):
        async with self.active_commands_lock:
            for index, rec in list(self.active_commands.items()):
                if not rec['future'].done():
                    self.logger.debug(
                        "%s notifying command at log index %d due to demotion", self.my_uri(), index
                    )
                    rec['future'].set_result(True)
                    rec['error_data'] = "Leader demoted during command execution"
                    rec['result'] = None
            self.active_commands.clear()




                    
