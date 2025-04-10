import time
import traceback
import logging
import json
from raftengine.api.log_api import LogRec, RecordCode
from raftengine.api.types import StateCode, SubstateCode
from raftengine.messages.append_entries import AppendResponseMessage
from raftengine.messages.request_vote import RequestVoteResponseMessage
from raftengine.states.base_state import BaseState

class Follower(BaseState):

    def __init__(self, hull):
        super().__init__(hull, StateCode.follower)
        # log is set in BaseState as is leader_uri
        # only used during voting for leadership
        # Needs to be as recent as configured maximum silence period, or we raise hell.
        # Pretend we just got a call, that gives possible actual leader time to ping us
        self.last_leader_contact = time.time()
        self.logger = logging.getLogger("Follower")

    async def start(self):
        await super().start()
        self.last_leader_contact = time.time()
        await self.hull.record_substate(SubstateCode.leader_unknown)
        await self.run_after(self.hull.get_election_timeout(), self.contact_checker)
        
    async def on_append_entries(self, message):
        self.last_leader_contact = time.time()
        self.logger.debug("%s append term=%d local_term=%d prev_index=%d local_index=%d, prev_term=%d, local_prev_term=%d, entry_count=%d",
                          self.my_uri(),
                          message.term,  await self.log.get_term(),
                          message.prevLogIndex, await self.log.get_last_index(),
                          message.prevLogTerm,  await self.log.get_last_term(),
                          len(message.entries))

        if message.term == await self.log.get_term() and self.leader_uri != message.sender:
            self.leader_uri = message.sender
            self.logger.info("%s accepting new leader %s", self.my_uri(),
                             self.leader_uri)
            await self.hull.record_substate(SubstateCode.joined_leader)
        # special case, unfortunately. If leader says 0/0, then we have to empty the log
        if message.prevLogIndex == 0 and await self.log.get_last_index() > 0:
            self.logger.warning("%s Leader says our log is junk, starting over", self.my_uri())
            await self.log.delete_all_from(0)
        elif message.term != await self.log.get_term():
            await self.send_no_sync_append_response(message)
            return
        elif await self.log.get_last_index() > message.prevLogIndex:
            our_rec = await self.log.read(message.prevLogIndex)
            if our_rec.term != message.prevLogTerm:
                self.logger.warning("%s Leader indicates invalid record after index %s, deleting",
                                    self.my_uri(), message.prevLogIndex)
                await self.log.delete_all_from(message.prevLogIndex + 1)
                await self.send_no_sync_append_response(message)
                return
            
        elif (await self.log.get_last_index() != message.prevLogIndex
              or await self.log.get_last_term() != message.prevLogTerm):
            await self.send_no_sync_append_response(message)
            return
        if len(message.entries) == 0:
            self.logger.debug("%s heartbeat from leader %s", self.my_uri(),
                              message.sender)
            await self.send_append_entries_response(message)
            await self.hull.record_substate(SubstateCode.got_heartbeat)
            if message.commitIndex >= await self.log.get_last_index():
                if message.commitIndex > await self.log.get_commit_index():
                    await self.new_leader_commit_index(message.commitIndex)
            return
        await self.hull.record_substate(SubstateCode.appending)
        recs = []
        for log_rec in message.entries:
            self.logger.info("%s Added record from leader at index %s",
                                self.my_uri(), log_rec.index)
            recs.append(await self.log.append(log_rec))
        await self.hull.record_substate(SubstateCode.replied_to_command)
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
                                      leaderId=self.leader_uri)
        await self.hull.send_response(message, reply)
        self.logger.info("%s out of sync with leader, sending %s",  self.my_uri(), reply)

    async def new_leader_commit_index(self, leader_commit_index):
        commit = await self.log.get_commit_index()
        self.logger.info("%s Leader commit index %d higher than ours %d ",
                            self.my_uri(), leader_commit_index, commit)
        if commit == 0:
            min_index = 1
        else:
            min_index = commit
        last_index = await self.log.get_last_index()
        max_index = min(leader_commit_index + 1, last_index + 1)
        for index in range(min_index, max_index):
            log_rec = await self.log.read(index)
            if not log_rec.committed:
                if log_rec.code == RecordCode.client_command:
                    await self.process_command_record(log_rec)
                else:
                    log_rec.committed = True
                    await self.log.replace(log_rec)
                
    async def process_command_record(self, log_record):
        result = None
        error_data = None
        await self.hull.record_substate(SubstateCode.running_command)
        try:
            command = log_record.command
            processor = self.hull.get_processor()
            result, error_data = await processor.process_command(command, log_record.serial)
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
        last_vote = await self.log.get_voted_for()
        if last_vote is not None:
            # we only vote once per term, unlike some dead people I know
            self.logger.info("%s voting false on %s, already voted for %s", self.my_uri(),
                             message.sender, last_vote)
            await self.send_vote_response_message(message, vote_yes=False)
            return
            
        # Leadership claims have to be for max log commit index of
        # at least the same as our local copy
        commit_index = await self.log.get_commit_index()
        if commit_index > 0:
            # If the messages claim for last committed log index or term are not at least as high
            # as our local values, then vote no.
            rec = await self.log.read(commit_index)
            if message.prevLogIndex < commit_index or message.term < rec.term:
                self.logger.info("%s voting false on %s", self.my_uri(),
                                 message.sender)
                vote = False
            else: # both term and index proposals are acceptable, so vote yes
                await self.log.set_voted_for(message.sender)
                self.logger.info("%s voting true for candidate %s", self.my_uri(), message.sender)
                vote = True
        else: # we don't have any entries, so everybody else wins
            await self.log.set_voted_for(message.sender)
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
        await self.log.set_voted_for(None) # in case we voted during the now expired term
        # Tell the base class method to route the message back to us as normal
        return message
        
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
        
    async def send_append_entries_response(self, message):
        append_response = AppendResponseMessage(sender=self.my_uri(),
                                                receiver=message.sender,
                                                term=await self.log.get_term(),
                                                success=True,
                                                maxIndex=await self.log.get_last_index(),
                                                prevLogIndex=message.prevLogIndex,
                                                prevLogTerm=message.prevLogTerm,
                                                leaderId=self.leader_uri)
        self.logger.debug("%s sending response %s", self.my_uri(), append_response)
        await self.hull.send_response(message, append_response)

    async def contact_checker(self):
        max_time = self.hull.get_election_timeout()
        e_time = time.time() - self.last_leader_contact
        if e_time > max_time:
            self.logger.debug("%s lost leader after %f", self.my_uri(), e_time)
            await self.leader_lost()
            return
        # reschedule
        await self.run_after(self.hull.get_election_timeout(), self.contact_checker)
    

