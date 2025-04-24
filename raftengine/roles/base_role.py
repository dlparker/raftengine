import asyncio
import logging
from raftengine.messages.append_entries import AppendEntriesMessage, AppendResponseMessage
from raftengine.messages.request_vote import RequestVoteMessage, RequestVoteResponseMessage
from raftengine.messages.pre_vote import PreVoteMessage, PreVoteResponseMessage
from raftengine.messages.power import TransferPowerMessage, TransferPowerResponseMessage
from raftengine.messages.cluster_change import MembershipChangeMessage, MembershipChangeResponseMessage, ChangeOp
from raftengine.api.types import RoleName, SubstateCode
    
class BaseRole:

    
    def __init__(self, hull, role_name):
        self.hull = hull
        self.role_name = role_name
        self.logger = logging.getLogger("BaseState")
        self.substate = SubstateCode.starting
        self.log = hull.get_log()
        self.stopped = False
        self.routes = None
        self.build_routes()
        self.leader_uri = None

    def build_routes(self):
        self.routes = dict()
        code = AppendEntriesMessage.get_code()
        route = self.on_append_entries
        self.routes[code] = route
        code = AppendResponseMessage.get_code()
        route = self.on_append_entries_response
        self.routes[code] = route
        code = RequestVoteMessage.get_code()
        route = self.on_vote_request
        self.routes[code] = route
        code = RequestVoteResponseMessage.get_code()
        route = self.on_vote_response
        self.routes[code] = route
        code = PreVoteMessage.get_code()
        route = self.on_pre_vote_request
        self.routes[code] = route
        code = PreVoteResponseMessage.get_code()
        route = self.on_pre_vote_response
        self.routes[code] = route
        code = TransferPowerMessage.get_code()
        route = self.on_transfer_power_message
        self.routes[code] = route
        code = TransferPowerResponseMessage.get_code()
        route = self.on_transfer_power_response
        self.routes[code] = route
        code = MembershipChangeMessage.get_code()
        route = self.on_membership_change_message
        self.routes[code] = route
        code = MembershipChangeResponseMessage.get_code()        
        route = self.on_membership_change_response
        self.routes[code] = route

    async def start(self):
        # child classes not required to have this method, but if they do,
        # they should call this one (i.e. super().start())
        self.stopped = False
        if self.role_name == "LEADER":
            self.leader_uri = self.my_uri()

    async def stop(self):
        # child classes not required to have this method, but if they do,
        # they should call this one (i.e. super().stop())
        self.stopped = True

    async def run_after(self, delay, target):
        await self.hull.role_run_after(delay, target)

    async def cancel_run_after(self):
        await self.hull.cancel_role_run_after()
        
    async def on_message(self, message):
        if self.stopped:
            self.logger.debug('%s received message from %s but currently stoppped, ignoring', self.my_uri(), message.sender)
            return
        if message.code not in (MembershipChangeMessage.get_code(), MembershipChangeResponseMessage.get_code()):
            if (message.term > await self.log.get_term()
                and message.code not in (PreVoteMessage.get_code(), PreVoteResponseMessage.get_code())):
                self.logger.debug('%s received message from higher term, calling self.term_expired',
                                  self.my_uri())
                res = await self.term_expired(message)
                if not res:
                    self.logger.debug('%s self.term_expired said no further processing required',
                                      self.my_uri())
                    # no additional handling of message needed
                    return None
        route = self.routes.get(message.get_code(), None)
        if route:
            return await route(message)

    async def on_append_entries(self, message):
        problem = 'append_entries not implemented in the class '
        problem += f'"{self.__class__.__name__}" at {self.my_uri()}, sending rejection'
        self.logger.warning(problem)
        await self.send_reject_append_response(message)
        await self.hull.record_message_problem(message, problem)

    async def on_append_entries_response(self, message):
        if self.role_name == "FOLLOWER":
            problem = 'append_entries_response not implemented in the class '
            problem += f'"{self.__class__.__name__}" at {self.my_uri()}, sending rejection'
            if hasattr(message, 'leaderId'):
                if message.term == await self.log.get_term() and self.leader_uri is None:
                    self.logger.debug('%s message says leader is %s, adopting', self.my_uri(), message.leaderId)
                    self.leader_uri = message.leaderId
                    await self.hull.set_leader_uri(self.leader_uri)
                    problem += f" except adopting leader {self.leader_uri}"
        self.logger.warning(problem)
        await self.hull.record_message_problem(message, problem)

    async def on_vote_request(self, message):
        problem = 'request_vote not implemented in the class '
        problem += f'"{self.__class__.__name__}" at {self.my_uri()}, sending rejection'
        self.logger.warning(problem)
        await self.send_reject_vote_response(message)
        await self.hull.record_message_problem(message, problem)

    async def on_vote_response(self, message):
        if self.role_name == "LEADER" and message.term == await self.log.get_term():
            self.logger.info('request_vote_response leftover from finished election, ignoring')
            return
        problem = 'request_vote_response not implemented in the class '
        problem += f'"{self.__class__.__name__}" at {self.my_uri()}, sending rejection'
        self.logger.warning(problem)
        await self.hull.record_message_problem(message, problem)
        
    async def on_pre_vote_request(self, message):
        if self.role_name == "LEADER" and not message.authorized:
            self.logger.info("%s pre voting false on %s, am leader and last check quorum succeeded", self.my_uri(),
                             message.sender)
            await self.send_pre_vote_response_message(message, vote_yes=False)
            return
        # if we are a follower, then we haven't timed out on leader contact,
        # so we should say no, we have a leader.
        if self.role_name == "FOLLOWER" and self.leader_uri is not None and not message.authorized:
            self.logger.info("%s pre voting false on %s, leader is in contact", self.my_uri(), message.sender)
            await self.send_pre_vote_response_message(message, vote_yes=False)
            return
        
        commit_index = await self.log.get_commit_index()
        if message.term <= await self.log.get_term():
            vote = False
            self.logger.info("%s pre voting false on %s on low term", self.my_uri(),
                             message.sender, message.term)
        elif commit_index == 0:
            # we don't have any committed entries, so anybody wins
            self.logger.info("%s voting true for candidate %s", self.my_uri(), message.sender)
            vote = True
        else:
            rec = await self.log.read(commit_index)
            if message.prevLogIndex < commit_index or message.prevLogTerm < rec.term:
                self.logger.info("%s pre voting false on %s", self.my_uri(),
                                 message.sender)
                vote = False
            else: # both term and index proposals are acceptable, so vote yes
                self.logger.info("%s pre voting true for candidate %s", self.my_uri(), message.sender)
                vote = True
        await self.send_pre_vote_response_message(message, vote_yes=vote)

    async def on_pre_vote_response(self, message):
        problem = 'pre_vote_response not implemented in the class '
        problem += f'"{self.__class__.__name__}" at {self.my_uri()}, sending rejection'
        self.logger.warning(problem)
        await self.hull.record_message_problem(message, problem)
        
    async def on_transfer_power_response(self, message):
        self.logger.info('%s transfer_power response requires no action, ignoring %s', self.my_uri(), str(message))
        
    async def on_transfer_power_message(self, message):
        if self.role_name != "LEADER":
            term =  await self.log.get_term()
            index = await self.log.get_last_index()
            last_term = await self.log.get_last_term()
            if message.term == term and message.prevLogIndex == index and message.prevLogTerm == last_term:
                self.logger.warning("%s recieved valid transfer of power messages, starting election", self.my_uri())
                await self.send_transfer_power_response_message(message, success=True)
                await self.hull.start_campaign(authorized=True)
        
    async def send_reject_append_response(self, message):
        leaderId = self.leader_uri
        reply = AppendResponseMessage(message.receiver,
                                      message.sender,
                                      term=await self.log.get_term(),
                                      success=False,
                                      maxIndex=await self.log.get_last_index(),
                                      prevLogTerm=message.prevLogTerm,
                                      prevLogIndex=message.prevLogIndex,
                                      leaderId=leaderId)
        await self.hull.send_response(message, reply)

    async def send_reject_vote_response(self, message):
        data = dict(response=False)
        reply = RequestVoteResponseMessage(message.receiver,
                                           message.sender,
                                           term=message.term,
                                           prevLogIndex=await self.log.get_last_index(),
                                           prevLogTerm=await self.log.get_last_term(),
                                           vote=False)
        await self.hull.send_response(message, reply)

    async def send_pre_vote_response_message(self, message, vote_yes=True):
        pre_vote_response = PreVoteResponseMessage(sender=self.my_uri(),
                                                   receiver=message.sender,
                                                   term=message.term,
                                                   prevLogIndex=await self.log.get_last_index(),
                                                   prevLogTerm=await self.log.get_last_term(),
                                                   vote=vote_yes)
        await self.hull.send_response(message, pre_vote_response)
        if vote_yes:
            await self.hull.record_substate(SubstateCode.pre_voting_yes)
        else:
            await self.hull.record_substate(SubstateCode.pre_voting_no)
        
    async def send_transfer_power_response_message(self, message, success=True):
        xfer_power_response = TransferPowerResponseMessage(sender=self.my_uri(),
                                                         receiver=message.sender,
                                                         term=message.term,
                                                         prevLogIndex=await self.log.get_last_index(),
                                                         prevLogTerm=await self.log.get_last_term(),
                                                         success=success)
        await self.hull.send_response(message, xfer_power_response)

    async def send_self_exit(self):
        message = MembershipChangeMessage(sender=self.my_uri(),
                                      receiver=self.leader_uri,
                                      op=ChangeOp.remove,
                                      target_uri=self.my_uri())
        await self.hull.send_message(message)
    
    async def on_membership_change_message(self, message):
        problem = 'pre_membership_change_message not implemented in the class '
        problem += f'"{self.__class__.__name__}" at {self.my_uri()}, sending rejection'
        self.logger.warning(problem)
        await self.hull.record_message_problem(message, problem)
        await self.send_membership_change_response_message(message, ok=False)
        
    async def on_membership_change_response(self, message):
        problem = 'pre_membership_change_respone not implemented in the class '
        problem += f'"{self.__class__.__name__}" at {self.my_uri()}, ignoring'
        self.logger.warning(problem)
        await self.hull.record_message_problem(message, problem)
        
    async def send_membership_change_response_message(self, message, ok=True):
        response = MembershipChangeResponseMessage(sender=self.my_uri(),
                                                   receiver=message.sender,
                                                   op=message.op,
                                                   target_uri=message.target_uri,
                                                   ok=ok)
        await self.hull.send_response(message, response)
        
    def my_uri(self):
        return self.hull.get_my_uri()

    def __repr__(self):
        return self.role_name
