import asyncio
import logging
from raftengine.messages.append_entries import AppendEntriesMessage, AppendResponseMessage
from raftengine.messages.request_vote import RequestVoteMessage, RequestVoteResponseMessage
from raftengine.api.types import StateCode, SubstateCode
    
class BaseState:
    
    def __init__(self, hull, state_code):
        self.hull = hull
        self.state_code = state_code
        self.logger = logging.getLogger("BaseState")
        self.substate = SubstateCode.starting
        self.log = hull.get_log()
        self.stopped = False
        self.routes = None
        self.build_routes()

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

    async def start(self):
        # child classes not required to have this method, but if they do,
        # they should call this one (i.e. super().start())
        self.stopped = False

    async def stop(self):
        # child classes not required to have this method, but if they do,
        # they should call this one (i.e. super().stop())
        self.stopped = True

    async def run_after(self, delay, target):
        await self.hull.state_run_after(delay, target)

    async def cancel_run_after(self):
        await self.hull.cancel_state_run_after()
        
    async def on_message(self, message):
        if message.term > await self.log.get_term():
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
        problem += f'"{self.__class__.__name__}", sending rejection'
        self.logger.warning(problem)
        await self.send_reject_append_response(message)
        await self.hull.record_message_problem(message, problem)

    async def on_append_entries_response(self, message):
        problem = 'append_entries_response not implemented in the class '
        problem += f'"{self.__class__.__name__}", ignoring'
        self.logger.warning(problem)
        await self.hull.record_message_problem(message, problem)

    async def on_vote_request(self, message):
        problem = 'request_vote not implemented in the class '
        problem += f'"{self.__class__.__name__}", sending rejection'
        self.logger.warning(problem)
        await self.send_reject_vote_response(message)
        await self.hull.record_message_problem(message, problem)

    async def on_vote_response(self, message):
        if self.state_code == "LEADER" and message.term == await self.log.get_term():
            self.logger.info('request_vote_response leftover from finished election, ignoring')
            return
        problem = 'request_vote_response not implemented in the class '
        problem += f'"{self.__class__.__name__}", sending rejection'
        self.logger.warning(problem)
        await self.hull.record_message_problem(message, problem)
        
    async def send_reject_append_response(self, message):
        data = dict(success=False,
                    last_index=await self.log.get_last_index(),
                    last_term=await self.log.get_last_term())
        if self.state_code == "FOLLOWER":
            leaderId = self.leader_uri
        else:
            leaderId = ''
        reply = AppendResponseMessage(message.receiver,
                                      message.sender,
                                      term=await self.log.get_term(),
                                      entries=message.entries,
                                      results=[],
                                      prevLogTerm=message.prevLogTerm,
                                      prevLogIndex=message.prevLogIndex,
                                      myPrevLogTerm=await self.log.get_last_term(),
                                      myPrevLogIndex=await self.log.get_last_index(),
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

    def my_uri(self):
        return self.hull.get_my_uri()

    def __repr__(self):
        return self.state_code
