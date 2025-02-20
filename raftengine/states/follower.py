import time
import traceback
import logging
import json
from raftengine.api.log_api import LogRec
from raftengine.api.types import StateCode, SubstateCode
from raftengine.messages.append_entries import AppendResponseMessage
from raftengine.messages.request_vote import RequestVoteResponseMessage
from raftengine.states.base_state import BaseState

class Follower(BaseState):

    def __init__(self, hull):
        super().__init__(hull, StateCode.follower)
        # log is set in BaseState as is leader_uri
        # only used during voting for leadership
        self.last_vote = None
        # Needs to be as recent as configured maximum silence period, or we raise hell.
        # Pretend we just got a call, that gives possible actual leader time to ping us
        self.last_leader_contact = time.time()
        self.logger = logging.getLogger("Follower")

    async def start(self):
        await super().start()
        self.last_leader_contact = time.time()
        await self.hull.record_substate(SubstateCode.leader_unknown)
        await self.run_after(self.hull.get_leader_lost_timeout(), self.contact_checker)
        
    async def on_append_entries(self, message):
        self.logger.debug("%s append term = %d prev_index = %d local_term = %d local_index = %d",
                          self.my_uri(),  message.term,
                          message.prevLogIndex, await self.log.get_term(), await self.log.get_last_index())

        # Very rare case, sender thinks it is leader but has old term, probably
        # a network partition, or some kind of latency problem with the claimant's
        # operations that made us have an election. Te1ll the sender it is not leader any more.
        if message.term < await self.log.get_term():
            await self.hull.record_substate(SubstateCode.older_term)
            await self.send_reject_append_response(message)
            return
        self.last_leader_contact = time.time()
        if (message.prevLogIndex == await self.log.get_last_index()
            and message.prevLogTerm == await self.log.get_last_term()
            and message.entries == []):
            if self.leader_uri != message.sender:
                self.leader_uri = message.sender
                self.last_vote = message
                self.logger.info("%s accepting new leader %s", self.my_uri(),
                                 self.leader_uri)
                await self.hull.record_substate(SubstateCode.joined_leader)
            else:
                self.logger.debug("%s heartbeat from leader %s", self.my_uri(),
                                  message.sender)
            await self.send_append_entries_response(message, None)
            await self.hull.record_substate(SubstateCode.got_heartbeat)
            if message.commitIndex > await self.log.get_local_commit_index():
                await self.new_leader_commit_index(message.commitIndex)
            return
        if (message.prevLogIndex != await self.log.get_last_index()
            or message.prevLogTerm != await self.log.get_last_term()):
            # we are not in sync at current log rec, ask leader to
            # send us something else that matches what we need.
            await self.ask_for_catchup(message)
            return
        
        await self.hull.record_substate(SubstateCode.appending)
        recs = []
        for log_rec in message.entries:
            # make sure we don't copy commit flag
            log_rec.local_committed = False
            if await self.log.get_last_index() >= log_rec.index:
                self.logger.warning("%s Leader record replacing our local record at index %s",
                                    self.my_uri(), log_rec.index)
                recs.append(await self.log.replace(log_rec))
            else:
                self.logger.warning("%s Leader record added at index %s",
                                    self.my_uri(), log_rec.index)
                recs.append(await self.log.append(log_rec))
        await self.hull.record_substate(SubstateCode.replied_to_command)
        await self.send_append_entries_response(message, recs)
        if message.commitIndex <= await self.log.get_last_index():
            if message.commitIndex > await self.log.get_local_commit_index():
                await self.new_leader_commit_index(message.commitIndex)
        return

    async def new_leader_commit_index(self, leader_commit_index):
        local_commit = await self.log.get_local_commit_index()
        self.logger.info("%s Leader commit index %d higher than ours %d ",
                            self.my_uri(), leader_commit_index, local_commit)
        if local_commit == 0:
            min_index = 1
        else:
            min_index = local_commit
        last_index = await self.log.get_last_index()
        max_index = min(leader_commit_index + 1, last_index + 1)
        for index in range(min_index, max_index):
            log_rec = await self.log.read(index)
            if not log_rec.local_committed:
                await self.process_command_record(log_rec)
                
    async def process_command_record(self, log_record):
        result = None
        error_data = None
        await self.hull.record_substate(SubstateCode.running_command)
        try:
            command = log_record.command
            processor = self.hull.get_processor()
            result, error_data = await processor.process_command(command)
            if error_data is None:
                self.logger.debug("processor ran no error")
                await self.hull.record_substate(SubstateCode.command_done)
            else:
                self.logger.warning("processor ran but had an error %s", error_data)
                await self.hull.record_substate(SubstateCode.command_error)
        except Exception as e:
            trace = traceback.format_exc()
            msg = f"supplied process_command caused exception {trace}"
            error_data = trace
            self.logger.error(trace)
            await self.hull.record_substate(SubstateCode.command_error)
        if error_data:
            result = error_data
            error_flag = True
        else:
            error_flag = False
        log_record.result = result
        log_record.error = error_flag
        if not error_flag:
            new_rec = await self.log.update_and_commit(log_record)
        else:
            new_rec = await self.log.replace(log_record)
    
    async def on_vote_request(self, message):
        if self.last_vote is not None:
            if self.last_vote.term >= message.term:
                # we only vote once per term, unlike some dead people I know
                self.logger.info("%s voting false on %s, already voted for %s", self.my_uri(),
                                 message.sender, self.last_vote.sender)
                await self.send_vote_response_message(message, vote_yes=False)
                return
            # we have a new vote with a higher term, so forget about the last term's vote
            self.last_vote = None
            
        # Leadership claims have to be for max log commit index of
        # at least the same as our local copy
        last_index = await self.log.get_last_index()
        # If the messages claim for log index or term are not at least as high
        # as our local values, then vote no.
        if message.prevLogIndex < last_index or message.term < await self.log.get_term():
            self.logger.info("%s voting false on %s", self.my_uri(),
                             message.sender)
            vote = False
        else: # both term and index proposals are acceptable, so vote yes
            self.last_vote = message
            self.logger.info("%s voting true for candidate %s", self.my_uri(), message.sender)
            vote = True
        await self.send_vote_response_message(message, vote_yes=vote)
            
    async def term_expired(self, message):
        # Raft protocol says all participants should record the highest term
        # value that they receive in a message. Always means an election has
        # happened and we are in the new term.
        # Followers never decide that a higher term is not valid
        await self.hull.record_substate(SubstateCode.newer_term)
        await self.log.set_term(message.term)
        # Tell the base class method to route the message back to us as normal
        return message

    async def ask_for_catchup(self, message):
        # figure out what to ask for based on what
        # leader sent
        target_index = None
        target_term = None
        my_last_index = await self.log.get_last_index()
        my_last_term = await self.log.get_last_term()
        if message.prevLogIndex == 0:
            if my_last_index > 0:
                await self.log.delete_all_from(1)
                assert message.prevLogIndex == await self.log.get_last_index()
                assert message.prevLogTerm == await self.log.get_last_term()
            target_index = 0
            target_term = 0
        elif message.prevLogIndex > my_last_index:
            # tell leader to back down
            target_index = my_last_index
            target_term = my_last_term
        elif message.prevLogIndex < my_last_index:
            # can happen if used to be leader and saved uncommitted
            # logs that did not get preserved across election
            rec = await self.log.read(message.prevLogIndex)
            if rec.term == message.prevLogTerm:
                # We are in sync on this record, prolly got
                # here through backdown method. Delete everything
                # with a higher index
                index = message.prevLogIndex + 1
                await self.log.delete_all_from(index)
                target_index = message.prevLogIndex
                target_term = message.prevLogTerm
                assert message.prevLogIndex == await self.log.get_last_index()
                assert message.prevLogTerm == await self.log.get_last_term()
                # we are in sync with current message, so reprocess it to
                # allow any logs in it to be save and continued with normal
                # catchup
                await self.on_message(message)
                return
        if target_index is None:
            # we are backing down, but no match yet
            target_index = message.prevLogIndex - 1
            if target_index == 0:
                target_term = 0
            else:
                rec = await self.log.read(target_index)
                target_term = rec.term
                
        self.logger.info("%s requesting catchup starting at index %d term %d", self.my_uri(),
                         target_index, target_term)
        await self.hull.record_substate(SubstateCode.need_catchup)
        append_response = AppendResponseMessage(sender=self.my_uri(),
                                                receiver=message.sender,
                                                recordIds=[],
                                                term=await self.log.get_term(),
                                                prevLogIndex=target_index,
                                                prevLogTerm=target_term,
                                                leaderId=self.leader_uri)
        await self.hull.send_response(message, append_response)
        
    async def leader_lost(self):
        await self.hull.record_substate(SubstateCode.leader_lost)
        await self.hull.start_campaign()
        
    async def send_vote_response_message(self, message, vote_yes=True):
        vote_response = RequestVoteResponseMessage(sender=self.my_uri(),
                                                   receiver=message.sender,
                                                   term=message.term,
                                                   prevLogIndex=await self.log.get_last_index(),
                                                   prevLogTerm=await self.log.get_last_term(),
                                                   vote=vote_yes)
        await self.hull.send_response(message, vote_response)
        if vote_yes:
            await self.hull.record_substate(SubstateCode.voting_yes)
        else:
            await self.hull.record_substate(SubstateCode.voting_no)
        
    async def send_append_entries_response(self, message, new_records):
        record_ids = []
        if new_records is not None:
            record_ids = [ rec.index for rec in new_records ]
        my_index = await self.log.get_last_index()
        my_term = await self.log.get_last_term()
        append_response = AppendResponseMessage(sender=self.my_uri(),
                                                receiver=message.sender,
                                                term=await self.log.get_term(),
                                                prevLogIndex=my_index,
                                                prevLogTerm=my_term,
                                                recordIds=record_ids,
                                                leaderId=self.leader_uri)
        if new_records is not None:
            self.logger.info("%s sending response %s", self.my_uri(), append_response)
        await self.hull.send_response(message, append_response)

    async def contact_checker(self):
        max_time = self.hull.get_leader_lost_timeout()
        e_time = time.time() - self.last_leader_contact
        if e_time > max_time:
            self.logger.debug("%s lost leader after %f", self.my_uri(), e_time)
            await self.leader_lost()
            return
        # reschedule
        await self.run_after(self.hull.get_leader_lost_timeout(), self.contact_checker)
    
