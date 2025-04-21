import asyncio
import random
import logging
from raftengine.states.base_state import BaseState
from raftengine.api.types import StateCode, SubstateCode
from raftengine.messages.request_vote import RequestVoteMessage

class Candidate(BaseState):

    def __init__(self, hull):
        super().__init__(hull, StateCode.candidate)
        self.term = None
        self.votes = dict()
        self.reply_count = 0
        self.logger = logging.getLogger("Candidate")

    async def start(self):
        self.term = await self.log.get_term()
        await super().start()
        await self.start_campaign()
        
    async def start_campaign(self):
        await self.hull.record_substate(SubstateCode.start_election)
        self.term += 1
        await self.log.set_term(self.term)
        self.reply_count = 0
        for node_id in self.hull.get_cluster_node_ids():
            if node_id == self.hull.get_my_uri():
                self.votes[node_id] = True
            else:
                self.votes[node_id] = None
                message = RequestVoteMessage(sender=self.hull.get_my_uri(),
                                             receiver=node_id,
                                             term=self.term,
                                             prevLogTerm=await self.log.get_term(),
                                             prevLogIndex=await self.log.get_last_index())
                await self.hull.send_message(message)
        timeout =self.hull.get_election_timeout()
        self.logger.debug("%s setting election timeout to %f", self.hull.get_my_uri(), timeout)
        await self.hull.record_substate(SubstateCode.no_votes_in)
        await self.run_after(timeout, self.election_timed_out)
        
    async def on_vote_response(self, message):
        if message.term < self.term:
            self.logger.info("candidate %s ignoring out of date vote", self.hull.get_my_uri())
            return
        self.votes[message.sender] = message.vote
        self.logger.info("candidate %s voting result %s from %s", self.hull.get_my_uri(),
                         message.vote, message.sender)
        self.reply_count += 1
        tally = 0
        for nid in self.votes:
            if self.votes[nid] == True:
                tally += 1
        self.logger.info("candidate %s voting results with %d votes in, wins = %d (includes self)",
                         self.hull.get_my_uri(), self.reply_count + 1, tally)
        if tally > len(self.votes) / 2:
            await self.cancel_run_after()
            await self.hull.win_vote(self.term)
            await self.hull.record_substate(SubstateCode.won)
            return
        if self.reply_count + 1 > len(self.votes) / 2:
            self.logger.info("candidate %s campaign lost, trying again", self.hull.get_my_uri())
            await self.cancel_run_after()
            await self.run_after(self.hull.get_election_timeout(), self.start_campaign)            
            await self.hull.record_substate(SubstateCode.start_new_election)
            return
        await self.hull.record_substate(SubstateCode.some_votes_in)

    async def term_expired(self, message):
        await self.hull.record_substate(SubstateCode.newer_term)
        await self.hull.demote_and_handle(message)
        return None

    async def on_append_entries(self, message):
        self.logger.info("candidate %s got append entries from %s", self.hull.get_my_uri(),
                         message.sender)
        # never get here if term is higher, we get called self.term_expired first
        if message.term == await self.log.get_term():
            await self.hull.record_substate(SubstateCode.lost)
            self.logger.info("candidate %s at term %d yielding to %s term %d", self.hull.get_my_uri(),
                             await self.log.get_term(), message.sender, message.term)
            await self.hull.demote_and_handle(message)
            return
        # if term was newer, we'd get term_expired call. if it was same about test
        # would catch it. So, term is older
        await self.hull.record_substate(SubstateCode.older_term)
        self.logger.warning("candidate %s at term %d got append_entries from  %s term %d",
                            self.hull.get_my_uri(),  await self.log.get_term(),
                            message.sender, message.term)
        await self.send_reject_append_response(message)
        
    async def election_timed_out(self):
        await self.hull.record_substate(SubstateCode.election_timeout)
        self.logger.info("--!!!!!--candidate %s campaign timedout, trying again", self.hull.get_my_uri())
        await self.start_campaign()
        
        


