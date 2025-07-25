import time
import traceback
import logging
import json
from raftengine.api.log_api import LogRec, RecordCode
from raftengine.api.types import RoleName, OpDetail
from raftengine.messages.append_entries import AppendResponseMessage
from raftengine.messages.request_vote import RequestVoteResponseMessage
from raftengine.messages.pre_vote import PreVoteResponseMessage
from raftengine.roles.base_role import BaseRole
from raftengine.messages.cluster_change import MembershipChangeMessage, ChangeOp
from raftengine.api.snapshot_api import SnapShot


class Follower(BaseRole):

    def __init__(self, deck, cluster_ops):
        super().__init__(deck, RoleName.follower, cluster_ops)
        # log is set in BaseState as is leader_uri
        # only used during voting for leadership
        # Needs to be as recent as configured maximum silence period, or we raise hell.
        # Pretend we just got a call, that gives possible actual leader time to ping us
        self.last_leader_contact = time.time()
        self.logger = logging.getLogger("Follower")
        self.elec_logger = logging.getLogger("Elections")
        self.snapshot = None
        
    async def start(self):
        await super().start()
        self.last_leader_contact = time.time()
        await self.run_after(await self.cluster_ops.get_election_timeout(), self.contact_checker)
        
    async def on_append_entries(self, message):
        self.last_leader_contact = time.time()
        self.logger.debug("%s append term=%d local_term=%d prev_index=%d local_index=%d, "
                          + "prev_term=%d, local_prev_term=%d, entry_count=%d",
                          self.my_uri(),
                          message.term,  await self.log.get_term(),
                          message.prevLogIndex, await self.log.get_last_index(),
                          message.prevLogTerm,  await self.log.get_last_term(),
                          len(message.entries))

        if message.term == await self.log.get_term() and self.leader_uri != message.sender:
            await self.deck.set_leader_uri(message.sender)
            self.elec_logger.info("%s accepting new leader %s", self.my_uri(),
                             self.leader_uri)
            await self.deck.record_op_detail(OpDetail.joined_leader)
        # special case, unfortunately. If leader says 0/0, then we have to empty the log
        if message.prevLogIndex == 0 and await self.log.get_last_index() > 0:
            self.logger.warning("%s Leader says our log is junk, starting over", self.my_uri())
            await self.delete_log_from(1)
        elif message.term != await self.log.get_term():
            await self.send_no_sync_append_response(message)
            return
        elif await self.log.get_last_index() > message.prevLogIndex:
            our_rec = await self.log.read(message.prevLogIndex)
            if our_rec.term != message.prevLogTerm:
                self.logger.warning("%s Leader indicates invalid record after index %s, deleting",
                                    self.my_uri(), message.prevLogIndex)
                await self.log.delete_all_from(message.prevLogIndex)
                await self.send_no_sync_append_response(message)
                return
            else:
                if len(message.entries) > 0 and await self.log.get_last_index() > message.prevLogIndex:
                    leader_rec = message.entries[0]
                    our_next_rec = await self.log.read(leader_rec.index)
                    self.logger.warning("%s Leader says rewrite at record pi=%d",  self.my_uri(), leader_rec.index)
                    await self.delete_log_from(leader_rec.index)
                    # fall through to append logic

        elif (await self.log.get_last_index() != message.prevLogIndex
              or await self.log.get_last_term() != message.prevLogTerm):
            await self.send_no_sync_append_response(message)
            return
        if len(message.entries) == 0:
            self.logger.debug("%s heartbeat from leader %s", self.my_uri(),
                              message.sender)
            await self.send_append_entries_response(message)
            if message.commitIndex >= await self.log.get_last_index():
                if (message.commitIndex > await self.log.get_commit_index()
                    or message.commitIndex > await self.log.get_applied_index()):
                    await self.new_leader_commit_index(message.commitIndex)
            return
        recs = []
        for log_rec in message.entries:
            # ensure we don't copy the items that reflect local state at the leader
            log_rec.committed = log_rec.applied = False
            self.logger.info("%s Added record from leader at index %s",
                                self.my_uri(), log_rec.index)
            new_rec = await self.log.append(log_rec)
            recs.append(new_rec)
            # config changes are applied immediately
            if log_rec.code == RecordCode.cluster_config:
                await self.cluster_ops.handle_membership_change_log_update(log_rec)
            elif log_rec.code == RecordCode.term_start and log_rec.index == 1:
                # At the start of the first term we update the cluster config to whatever the
                # leader has. Any changes will come in cluster_config record types
                await self.cluster_ops.update_cluster_config_from_json_string(log_rec.command)
        await self.send_append_entries_response(message)
        if message.commitIndex >= await self.log.get_last_index():
            if message.commitIndex > await self.log.get_commit_index():
                await self.new_leader_commit_index(message.commitIndex)
        return

    async def send_no_sync_append_response(self, message):
        reply = AppendResponseMessage(message.receiver,
                                      message.sender,
                                      term=await self.log.get_term(),
                                      success=False,
                                      maxIndex=await self.log.get_last_index(),
                                      prevLogTerm=message.prevLogTerm,
                                      prevLogIndex=message.prevLogIndex,
                                      original_serial=message.serial_number,
                                      leaderId=self.leader_uri)
        await self.deck.send_response(message, reply)
        self.logger.warning("%s out of sync with leader, sending %s",  self.my_uri(), reply)

    async def new_leader_commit_index(self, leader_commit_index):
        commit = await self.log.get_commit_index()
        commit = min(commit, await self.log.get_applied_index())
        if commit == 0:
            min_index = 1
        else:
            min_index = commit + 1

        last_index = await self.log.get_last_index()
        max_index = min(leader_commit_index + 1, last_index + 1)
        self.logger.info("%s Leader commit index %d higher than ours %d, committing and applying from %d through %d ",
                            self.my_uri(), leader_commit_index, commit, min_index, max_index-1)
        for index in range(min_index, max_index):
            log_rec = await self.log.read(index)
            if not log_rec.committed:
                await self.log.update_and_commit(log_rec)
                self.logger.debug("%s committing %d ", self.my_uri(), log_rec.index)
        for index in range(min_index, max_index):
            log_rec = await self.log.read(index)
            if log_rec.code == RecordCode.client_command:
                if not log_rec.applied:
                    self.logger.debug("%s applying command at record %d ", self.my_uri(), log_rec.index)
                    await self.process_command_record(log_rec)
            if log_rec.code == RecordCode.cluster_config:
                if not log_rec.applied:
                    self.logger.debug("%s applying cluster config qt record %d ", self.my_uri(), log_rec.index)
                    await self.process_cluster_ops(log_rec)
                
    async def process_cluster_ops(self, log_record):
        if not log_record.applied:
            await self.cluster_ops.handle_membership_change_log_commit(log_record)
            log_record.applied = True
            await self.log.replace(log_record)

    async def process_command_record(self, log_record):
        result = None
        error_data = None
        try:
            command = log_record.command
            processor = self.deck.get_processor()
            result, error_data = await processor.process_command(command, log_record.serial)
        except Exception as e:
            trace = traceback.format_exc()
            msg = f"supplied process_command caused exception {trace}"
            error_data = trace
            self.logger.error(trace)
            await self.deck.event_control.emit_error(error_data)
        if error_data:
            result = error_data
            error_flag = True
        else:
            error_flag = False
        log_record.result = result
        log_record.error = error_flag
        if not error_flag:
            await self.log.update_and_apply(log_record)
            self.logger.debug("%s processor ran no error on log record %d", self.my_uri(), log_record.index)
        else:
            await self.log.replace(log_record)
            self.logger.warning("processor ran but had an error %s", error_data)
            await self.deck.event_control.emit_error(error_data)
    
    async def on_vote_request(self, message):
        last_vote = await self.log.get_voted_for()
        if last_vote is not None:
            # we only vote once per term, unlike some dead people I know
            self.elec_logger.info("%s voting false on %s, already voted for %s", self.my_uri(),
                             message.sender, last_vote)
            await self.send_vote_response_message(message, vote_yes=False)
            return
            
        # Leadership claims have to be for max log index of
        # at least the same as our local copy
        local_index = await self.log.get_last_index()
        local_term = await self.log.get_last_term()
        if local_index > 0:
            # If the messages claim for last committed log index or term are not at least as high
            # as our local values, then vote no.
            if message.prevLogIndex < local_index or message.prevLogTerm < local_term:
                self.elec_logger.info("%s voting false on %s", self.my_uri(),
                                 message.sender)
                vote = False
            else: # both term and index proposals are acceptable, so vote yes
                await self.log.set_voted_for(message.sender)
                self.elec_logger.info("%s voting true for candidate %s", self.my_uri(), message.sender)
                vote = True
        else: # we don't have any entries, so everybody else wins
            await self.log.set_voted_for(message.sender)
            self.elec_logger.info("%s voting true for candidate %s", self.my_uri(), message.sender)
            vote = True
        await self.send_vote_response_message(message, vote_yes=vote)

    async def delete_log_from(self, index):
        cur_index = await self.log.get_last_index()
        while cur_index >= index:
            rec = await self.log.read(cur_index)
            if rec.code == RecordCode.cluster_config:
                self.logger.warning("%s reversing config change record at %d", self.my_uri(), rec.index)
                await self.cluster_ops.reverse_config_change(rec)
            await self.log.delete_all_from(cur_index)
            cur_index -= 1
            
    async def join_cluster(self, leader_uri):
        message = MembershipChangeMessage(sender=self.my_uri(),
                                          receiver=leader_uri,
                                          op=ChangeOp.add,
                                          target_uri=self.my_uri())
        await self.deck.send_message(message)
        
    async def term_expired(self, message):
        # Raft protocol says all participants should record the highest term
        # value that they receive in a message. Always means an election has
        # happened and we are in the new term.
        # Followers never decide that a higher term is not valid
        await self.deck.record_op_detail(OpDetail.newer_term)
        await self.deck.set_term(message.term)
        await self.log.set_voted_for(None) # in case we voted during the now expired term
        # Tell the base class method to route the message back to us as normal
        return message
        
    async def leader_lost(self):
        self.elec_logger.info("%s Lost contact with leader, starting election", self.my_uri())
        await self.deck.record_op_detail(OpDetail.leader_lost)
        await self.log.set_voted_for(None) # in case we voted during the now expired term
        await self.deck.start_campaign()
        
    async def send_vote_response_message(self, message, vote_yes=True):
        vote_response = RequestVoteResponseMessage(sender=self.my_uri(),
                                                   receiver=message.sender,
                                                   term=message.term,
                                                   prevLogIndex=await self.log.get_last_index(),
                                                   prevLogTerm=await self.log.get_last_term(),
                                                   vote=vote_yes)
        await self.deck.send_response(message, vote_response)
        
    async def send_append_entries_response(self, message):
        append_response = AppendResponseMessage(sender=self.my_uri(),
                                                receiver=message.sender,
                                                term=await self.log.get_term(),
                                                success=True,
                                                maxIndex=await self.log.get_last_index(),
                                                prevLogIndex=message.prevLogIndex,
                                                prevLogTerm=message.prevLogTerm,
                                                original_serial=message.serial_number,
                                                leaderId=self.leader_uri)
        self.logger.debug("%s sending response %s", self.my_uri(), append_response)
        await self.deck.send_response(message, append_response)

    async def contact_checker(self):
        max_time = await self.cluster_ops.get_election_timeout()
        e_time = time.time() - self.last_leader_contact
        if e_time > max_time:
            self.elec_logger.info("%s lost leader after %f", self.my_uri(), e_time)
            await self.leader_lost()
            return
        # reschedule
        await self.run_after(await self.cluster_ops.get_election_timeout(), self.contact_checker)

    async def on_snapshot_message(self, message):
        if message.term == await self.log.get_term():
            if self.snapshot is None:
                self.logger.info("%s starting snapshot import %s", self.my_uri(), message)
                self.snapshot =  SnapShot(message.prevLogIndex, message.prevLogTerm)
                self.snapshot_tool = await self.deck.pilot.begin_snapshot_import(self.snapshot)
                config = message.clusterConfig
                await self.cluster_ops.update_cluster_config_from_json_string(config)
            self.logger.info("%s importing snapshot chunk %s", self.my_uri(), message)
            await self.snapshot_tool.load_snapshot_chunk(message.data)
            if message.done:
                self.logger.info("%s applying imported snapshot %s", self.my_uri(), message)
                await self.snapshot_tool.apply_snapshot()
                self.snapshot = None
                self.snapshot_tool = None
            await self.send_snapshot_response_message(message, True)

