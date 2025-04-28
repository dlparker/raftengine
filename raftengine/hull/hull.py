import asyncio
import traceback
import logging
import time
import json

from raftengine.api.types import RoleName
from raftengine.api.hull_api import CommandResult
from raftengine.hull.event_control import EventControl
from raftengine.messages.request_vote import RequestVoteMessage,RequestVoteResponseMessage
from raftengine.messages.pre_vote import PreVoteMessage,PreVoteResponseMessage
from raftengine.messages.append_entries import AppendEntriesMessage, AppendResponseMessage
from raftengine.messages.power import TransferPowerMessage, TransferPowerResponseMessage
from raftengine.messages.cluster_change import MembershipChangeMessage, MembershipChangeResponseMessage, ChangeOp
from raftengine.roles.follower import Follower
from raftengine.roles.candidate import Candidate
from raftengine.roles.leader import Leader
from raftengine.api.pilot_api import PilotAPI
from raftengine.api.hull_api import HullAPI
from raftengine.api.events import EventType
from raftengine.api.hull_config import ClusterInitConfig, LocalConfig
from raftengine.hull.cluster_ops import ClusterOps

class Hull(HullAPI):

    # Part of API
    def __init__(self, cluster_config: ClusterInitConfig, local_config: LocalConfig, pilot: PilotAPI):
        self.cluster_init_config = cluster_config
        self.local_config = local_config
        if not isinstance(pilot, PilotAPI):
            raise Exception('Must supply a raftengine.hull.api.PilotAPI implementation')
        self.pilot = pilot
        self.started = False
        self.log = pilot.get_log()
        self.logger = logging.getLogger("Hull")
        self.role_async_handle = None
        self.role_run_after_target = None
        self.message_problem_history = []
        self.log_substates = logging.getLogger("Substates")
        self.event_control = EventControl()
        self.cluster_ops = ClusterOps(self, cluster_config, self.log)
        self.role = Follower(self, self.cluster_ops)
        self.joining_cluster = False
        self.join_result = None
        
    # Part of API
    async def start(self):
        await self.cluster_ops.get_cluster_config()
        self.started = True
        await self.role.start()
        if EventType.role_change in self.event_control.active_events:
            await self.event_control.emit_role_change(self.get_role_name())

    def get_cluster_ops(self):
        if not self.started:
            return None
        return self.cluster_ops

    def get_role(self):
        return self.role

    async def note_join_done(self, success):
        self.join_result = success
        self.logger.warning("%s join leader result is %s", self.get_my_uri(), self.join_result)
        
    async def join_waiter(self, timeout, callback=None):
        start_time = time.time()
        while time.time() - start_time < timeout and self.join_result is None:
            await asyncio.sleep(0.001)
        ok = self.join_result
        self.join_result = None
        if ok is None:
            # timeout
            ok = False
            etime  = time.time() - start_time
            self.logger.warning("%s attempt to join leader timedout after %f", self.get_my_uri(), etime)
        if ok:
            if EventType.membership_change_complete in self.event_control.active_events:
                await self.event_control.emit_membership_change_complete(ChangeOp.add, self.get_my_uri())
        else:
            if EventType.membership_change_aborted in self.event_control.active_events:
                await self.event_control.emit_membership_change_aborted(ChangeOp.add, self.get_my_uri())
        if callback:
            await callback(ok ,self.get_my_uri())
        self.joining_cluster = False
        if not ok:
            await self.stop()

    async def start_and_join(self, leader_uri, callback=False, timeout=10.0):
        self.joining_cluster = True
        config = await self.cluster_ops.get_cluster_config()
        if leader_uri not in config.nodes:
            raise Exception(f'cannot find specified leader {leader_uri} in cluster {self.cluster_ops.get_cluster_node_ids()}')
        await self.role.start()
        if EventType.role_change in self.event_control.active_events:
            await self.event_control.emit_role_change(self.get_role_name())
        self.join_result = None
        await self.role.join_cluster(leader_uri)
        asyncio.create_task(self.join_waiter(timeout, callback))
        
    # Part of API
    def decode_message(self, in_message):
        mdict = json.loads(in_message)
        mtypes = [AppendEntriesMessage,AppendResponseMessage,
                  RequestVoteMessage,RequestVoteResponseMessage,
                  PreVoteMessage,PreVoteResponseMessage,
                  TransferPowerMessage,TransferPowerResponseMessage,
                  MembershipChangeMessage,MembershipChangeResponseMessage,]
                  
        message = None
        for mtype in mtypes:
            if mdict['code'] == mtype.get_code():
                message = mtype.from_dict(mdict)
        if message is None:
            raise Exception('Message is not decodeable as a raft type')
        return message
    
    # Part of API
    async def on_message(self, in_message):
        try:
            message = self.decode_message(in_message)
            if EventType.msg_recv in self.event_control.active_events:
                await self.event_control.emit_recv_msg(message)
        except:
            error = traceback.format_exc()
            self.logger.error(error)
            await self.record_message_problem(in_message, error)
            if EventType.error in self.event_control.active_events:
                await self.event_control.emit_error(error)
            return None
        res = await self.inner_on_message(message)
        return res
        
    async def inner_on_message(self, message):
        res = None
        error = None
        try:
            self.logger.debug("%s Handling message type %s", self.get_my_uri(), message.get_code())
            res = await self.role.on_message(message)
        except Exception as e:
            error = traceback.format_exc()
            self.logger.error(error)
        if EventType.msg_handled in self.event_control.active_events:
            await self.event_control.emit_handled_msg(message, result=res, error=error)
        if error:
            if EventType.error in self.event_control.active_events:
                await self.event_control.emit_error(error)
            await self.record_message_problem(message, error)
        return res

    # Part of API
    async def run_command(self, command, timeout=1):
        if EventType.index_change in self.event_control.active_events:
            orig_log = await self.log.read()
        if EventType.commit_change in self.event_control.active_events:
            orig_commit = await self.log.get_commit_index()
        if self.role.role_name == RoleName.leader:
            result = await self.role.run_command(command, timeout=timeout)
        elif self.role.role_name == RoleName.follower:
            result = CommandResult(command, redirect=self.leader_uri)
        elif self.role.role_name == RoleName.candidate:
            result = CommandResult(command, retry=1)
        if EventType.index_change in self.event_control.active_events:
            new_log = await self.log.read()
            if new_log.index > orig_log.index:
                await self.event_control.emit_index_change(new_log.index)
        if EventType.commit_change in self.event_control.active_events:
            new_commit = await self.log.get_commit_index()
            if orig_commit != new_commit:
                await self.event_control.emit_commit_change(new_commit)
        return result

    # Part of API
    async def add_event_handler(self, handler):
        return self.event_control.add_handler(handler)
    
    # Part of API
    async def remove_event_handler(self, handler):
        return self.event_control.remove_handler(handler)
    
    # Called by Role
    def get_log(self):
        return self.log

    # Called by Role
    def get_role_name(self):
        return self.role.role_name

    # Called by Role
    def get_my_uri(self):
        return self.local_config.uri
        
    # Called by Role
    def get_processor(self):
        return self.pilot

    @property
    def leader_uri(self):
        return self.cluster_ops.leader_uri
    
    # Called by Role
    async def set_leader_uri(self, uri):
        self.cluster_ops.leader_uri = uri
        if EventType.leader_change in self.event_control.active_events:
            await self.event_control.emit_leader_change(uri)
    
    # Called by Role and in API
    async def get_term(self):
        return await self.log.get_term()

    # Called by Role and in API
    async def set_term(self, term):
        if EventType.term_change in self.event_control.active_events:
            await self.event_control.emit_term_change(term)
        return await self.log.set_term(term)

    # Called by  API
    async def get_cluster_config(self):
        return await self.cluster_ops.get_cluster_config()
    
    # Called by Role and in API
    def get_cluster_node_ids(self):
        return self.cluster_ops.get_cluster_node_ids()

    # Called by Role and in API
    async def get_heartbeat_period(self):
        return await self.cluster_ops.get_heartbeat_period()

    # Called by Role and in API
    async def get_election_timeout(self):
        return await self.cluster_ops.get_election_timeou()

    # Called by Role 
    async def get_election_timeout_range(self):
        return await self.cluster_ops.get_election_timeout_range()

    # Called by Role
    async def get_max_entries_per_message(self):
        return await self.cluster_ops.get_max_entries_per_message()

    # Part of API 
    async def exit_cluster(self):
        if self.role.role_name == "LEADER":
            await self.role.do_node_exit(self.get_my_uri())
        else:
            await self.role.send_self_exit()
        
    # Part of API 
    async def stop(self):
        await self.stop_role()

    async def stop_role(self):
        await self.role.stop()
        if self.role_async_handle:
            self.logger.debug("%s canceling scheduled task", self.get_my_uri())
            self.role_async_handle.cancel()
            self.role_async_handle = None

    async def exiting_cluster(self):
        await self.pilot.stop_commanded()
        if not self.role.role_name == "FOLLOWER":
            await self.stop_role()
            self.role = Follower(self, self.cluster_ops)
        await self.role.stop()
            
    # Called by Role
    async def transfer_power(self, other_uri):
        if self.role.role_name == "LEADER":
            return await self.role.transfer_power(other_uri)
        self.logger.error("%s got call to transfer power but not leader", self.get_my_uri())
        raise Exception(f"got call to transfer power but not leader")

    # Called by Role
    async def start_campaign(self, authorized=False):
        await self.stop_role()
        config = await self.cluster_ops.get_cluster_config()
        self.role = Candidate(self, self.cluster_ops, use_pre_vote=config.settings.use_pre_vote, authorized=authorized)
        await self.role.start()
        if EventType.role_change in self.event_control.active_events:
            await self.event_control.emit_role_change(self.get_role_name())
        self.logger.warning("%s started campaign term = %s pre_vote=%s", self.get_my_uri(),
                            await self.log.get_term(), config.settings.use_pre_vote)

    # Called by Role
    async def win_vote(self, new_term):
        await self.stop_role()
        config = await self.cluster_ops.get_cluster_config()
        self.role = Leader(self, self.cluster_ops, new_term, config.settings.use_check_quorum)
        await self.set_leader_uri(self.get_my_uri())
        self.logger.warning("%s promoting to leader for term %s", self.get_my_uri(), new_term)
        await self.role.start()
        if EventType.role_change in self.event_control.active_events:
            await self.event_control.emit_role_change(self.get_role_name())

    # Called by Role
    async def demote_and_handle(self, message=None):
        self.logger.warning("%s demoting from %s to follower", self.get_my_uri(), self.role)
        await self.stop_role()
        self.role = Follower(self, self.cluster_ops)
        await self.role.start()
        if EventType.role_change in self.event_control.active_events:
            await self.event_control.emit_role_change(self.get_role_name())
        if message and hasattr(message, 'leaderId'):
            self.logger.debug('%s message says leader is %s, adopting', self.get_my_uri(), message.leaderId)
            await self.set_leader_uri(message.leaderId)
        if message:
            self.logger.warning('%s reprocessing message as follower %s', self.get_my_uri(), message)
            return await self.inner_on_message(message)

    # Called by Role
    async def send_message(self, message):
        self.logger.debug("Sending message type %s to %s", message.get_code(), message.receiver)
        encoded = json.dumps(message, default=lambda o:o.__dict__)
        await self.pilot.send_message(message.receiver, encoded)
        if EventType.msg_sent in self.event_control.active_events:
            await self.event_control.emit_sent_msg(message)

    # Called by Role
    async def send_response(self, message, response):
        self.logger.debug("Sending response type %s to %s", response.get_code(), response.receiver)
        encoded = json.dumps(message, default=lambda o:o.__dict__)
        encoded_reply = json.dumps(response, default=lambda o:o.__dict__)
        await self.pilot.send_response(response.receiver, encoded, encoded_reply)
        if EventType.msg_sent in self.event_control.active_events:
            await self.event_control.emit_sent_msg(message)

    # Called by Role. This may seem odd, but it is done this
    # way to make it possible to protect against race conditions where a role
    # instance is shutting down but the timer that it has set fires during shutdown.
    # The actually happened during testing and it leads to some nasty logic conflicts.
    # Better to circumvent it by running the actual timers and callbacks in this
    # class, which never goes away.
    async def role_run_after(self, delay, target):
        delay += 0.0
        if self.role_async_handle:
            self.logger.debug('%s cancelling after target to %s', self.local_config.uri,
                        self.role_run_after_target)
            self.role_async_handle.cancel()
        self.logger.debug('%s setting run after target to %s after %0.8f', self.local_config.uri, target, delay)
        self.role_run_after_target = target
        loop = asyncio.get_event_loop()
        self.role_async_handle = loop.call_later(delay,
                                                  lambda target=target:
                                                  asyncio.create_task(self.role_after_runner(target)))

    # see comments above in role_run_after
    async def role_after_runner(self, target):
        if self.role.stopped or self.joining_cluster:
            return
        await target()
        
    # Called by Role
    # see comments above in role_run_after
    async def cancel_role_run_after(self):
        if self.role_async_handle:
            self.role_async_handle.cancel()
            self.role_async_handle = None
        
    # Called by Role
    async def record_message_problem(self, message, problem):
        rec = dict(problem=problem, message=message)
        self.message_problem_history.append(rec)

    # Called by Role
    async def record_substate(self, substate):
        rec = dict(role=str(self.role), substate=substate, time=time.time())
        if self.log_substates:
            self.log_substates.debug("%s %s %s %s", self.get_my_uri(), rec['role'], rec['substate'], rec['time'])

    def get_message_problem_history(self, clear=False):
        res =  self.message_problem_history
        if clear:
            self.message_problem_history = []
        return res


