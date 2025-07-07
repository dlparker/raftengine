import asyncio
import traceback
import logging
import time
import json

from raftengine.api.types import RoleName, OpDetail, ClusterSettings, ClusterConfig
from raftengine.api.deck_api import CommandResult
from raftengine.api.snapshot_api import SnapShot, SnapShotToolAPI
from raftengine.deck.event_control import EventControl
from raftengine.messages.request_vote import RequestVoteMessage,RequestVoteResponseMessage
from raftengine.messages.pre_vote import PreVoteMessage,PreVoteResponseMessage
from raftengine.messages.append_entries import AppendEntriesMessage, AppendResponseMessage
from raftengine.messages.power import TransferPowerMessage, TransferPowerResponseMessage
from raftengine.messages.cluster_change import MembershipChangeMessage, MembershipChangeResponseMessage, ChangeOp
from raftengine.messages.snapshot import SnapShotMessage, SnapShotResponseMessage
from raftengine.roles.follower import Follower
from raftengine.roles.candidate import Candidate
from raftengine.roles.leader import Leader
from raftengine.api.pilot_api import PilotAPI
from raftengine.api.deck_api import DeckAPI
from raftengine.api.events import EventType
from raftengine.api.deck_config import ClusterInitConfig, LocalConfig
from raftengine.deck.cluster_ops import ClusterOps

class Deck(DeckAPI):

    # Part of API
    def __init__(self, initial_cluster_config: ClusterInitConfig, local_config: LocalConfig, pilot: PilotAPI):
        self.local_config = local_config
        if not isinstance(pilot, PilotAPI):
            raise Exception('Must supply a raftengine.deck.api.PilotAPI implementation')
        self.pilot = pilot
        self.started = False
        self.log = pilot.get_log()
        self.logger = logging.getLogger("Deck")
        self.role_async_handle = None
        self.role_run_after_target = None
        self.message_problem_history = []
        self.log_substates = logging.getLogger("Substates")
        self.event_control = EventControl()
        self.cluster_ops = ClusterOps(self, initial_cluster_config, self.log)
        self.role = Follower(self, self.cluster_ops)
        self.joining_cluster = False
        self.join_result = None
        self.join_waiter_handle = None
        self.exiting_cluster = False
        self.exit_result = None
        self.exit_waiter_handle = None
        self.stopped = False
        
    # Part of API
    async def start(self):
        await self.cluster_ops.get_cluster_config()
        self.started = True
        await self.role.start()
        if EventType.role_change in self.event_control.active_events:
            await self.event_control.emit_role_change(self.get_role_name())

    def get_cluster_ops(self):
        return self.cluster_ops

    def get_role(self):
        return self.role

    # Part of API
    async def get_leader_uri(self):
        # just in case it has never been called
        await self.cluster_ops.get_cluster_config()
        return self.cluster_ops.leader_uri

    def is_leader(self):
        if self.role.role_name == "LEADER":
            return True
        return False
        
    async def note_join_done(self, success):
        self.join_result = success
        self.logger.warning("%s join leader result is %s", self.get_my_uri(), self.join_result)
        
    async def join_waiter(self, timeout, callback=None):
        start_time = time.time()
        while time.time() - start_time < timeout and self.join_result is None and self.joining_cluster:
            await asyncio.sleep(0.001)

        if not self.joining_cluster:
            self.join_waiter_handle = None
            return
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
        self.join_waiter_handle = None
        
    # Part of API
    async def start_and_join(self, leader_uri, callback=False, timeout=10.0):
        config = await self.cluster_ops.get_cluster_config()
        if leader_uri not in config.nodes:
            raise Exception(f'cannot find specified leader {leader_uri} in cluster {self.cluster_ops.get_cluster_node_ids()}')
        self.joining_cluster = True
        await self.start()
        self.join_result = None
        await self.role.join_cluster(leader_uri)
        loop = asyncio.get_event_loop()
        self.logger.info("%s trying to join cluster via leader %s, starting join_waiter", self.get_my_uri(), leader_uri)
        self.join_waiter_handle = loop.call_soon(lambda timeout=timeout, callback=callback:
                                                asyncio.create_task(self.join_waiter(timeout, callback)))
        
    # Part of API
    def decode_message(self, in_message):
        mdict = json.loads(in_message)
        mtypes = [AppendEntriesMessage,AppendResponseMessage,
                  RequestVoteMessage,RequestVoteResponseMessage,
                  PreVoteMessage,PreVoteResponseMessage,
                  TransferPowerMessage,TransferPowerResponseMessage,
                  MembershipChangeMessage,MembershipChangeResponseMessage,
                  SnapShotMessage,SnapShotResponseMessage,]
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
        if error:
            if EventType.error in self.event_control.active_events:
                await self.event_control.emit_error(error)
            await self.record_message_problem(message, error)
        return res

    # Part of API
    async def run_command(self, command, timeout=1):
        if self.role.role_name == RoleName.leader:
            result = await self.role.run_command(command, timeout=timeout)
        elif self.role.role_name == RoleName.follower:
            result = CommandResult(command, redirect=self.leader_uri)
        elif self.role.role_name == RoleName.candidate:
            result = CommandResult(command, retry=1)
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
        return await self.cluster_ops.get_election_timeout()

    # Called by Role 
    async def get_election_timeout_range(self):
        return await self.cluster_ops.get_election_timeout_range()

    # Called by Role
    async def get_max_entries_per_message(self):
        return await self.cluster_ops.get_max_entries_per_message()

    async def note_exit_done(self, success):
        self.exit_result = success
        self.logger.warning("%s exit call to leader result is %s", self.get_my_uri(), self.exit_result)
        
    async def exit_waiter(self, timeout, callback=None):
        start_time = time.time()
        while time.time() - start_time < timeout and self.exit_result is None and self.exiting_cluster:
            await asyncio.sleep(0.001)
        self.logger.debug("%s detected exit result %s", self.get_my_uri(), self.exit_result)
        if not self.exiting_cluster:
            self.exit_waiter_handle = None
            return
        ok = self.exit_result
        self.exit_result = None
        if ok is None:
            # timeout
            ok = False
            etime  = time.time() - start_time
            self.logger.warning("%s attempt to exit leader timedout after %f", self.get_my_uri(), etime)
        if ok:
            if EventType.membership_change_complete in self.event_control.active_events:
                await self.event_control.emit_membership_change_complete(ChangeOp.remove, self.get_my_uri())
        else:
            if EventType.membership_change_aborted in self.event_control.active_events:
                await self.event_control.emit_membership_change_aborted(ChangeOp.remove, self.get_my_uri())
        if callback:
            await callback(ok ,self.get_my_uri())
        self.exiting_cluster = False
        if ok:
            self.exit_waiter_handle = None
            await self.stop()

    # Part of API
    async def take_snapshot(self, timeout=2.0) -> SnapShot:
        if self.role.role_name == "LEADER":
            nodes = self.cluster_ops.get_cluster_node_ids()
            target = None
            for uri in nodes:
                if uri != self.get_my_uri():
                    target = uri
                    break
            await self.role.transfer_power(target)
            start_time = time.time()
            while time.time() - start_time < timeout and self.role.role_name == "LEADER":
                await asyncio.sleep(0.001)
            if self.role.role_name == "LEADER":
                raise Exception("could not start snapshot, node is leader and transfer power failed")
        await self.role.stop()
        index = await self.log.get_applied_index()
        rec = await self.log.read(index)
        term = rec.term
        snapshot = await self.pilot.create_snapshot(index, term)
        await self.log.install_snapshot(snapshot)
        self.role = Follower(self, self.cluster_ops)
        await self.role.start()
        return snapshot
    
    # Part of API 
    async def exit_cluster(self, callback=None, timeout=10.0):
        self.exiting_cluster = True
        self.exit_result = None
        if self.role.role_name == "LEADER":
            await self.role.do_node_exit(self.get_my_uri())
        else:
            await self.role.send_self_exit()
        loop = asyncio.get_event_loop()
        leader_uri = await self.get_leader_uri()
        self.logger.info("%s trying to exit cluster via leader %s, starting exit_waiter", self.get_my_uri(), leader_uri)
        self.exit_waiter_handle = loop.call_soon(lambda timeout=timeout, callback=callback:
                                                asyncio.create_task(self.exit_waiter(timeout, callback)))
        await asyncio.sleep(0)
        
    # Part of API 
    async def update_settings(self, settings):
        if self.role.role_name != "LEADER":
            raise Exception("must only call at leader")
        await self.role.do_update_settings(settings)
    # Part of API
    def get_message_problem_history(self, clear=False):
        res =  self.message_problem_history
        if clear:
            self.message_problem_history = []
        return res

    # Part of API
    async def stop(self):
        await self.stop_role()
        if self.join_waiter_handle:
            self.joining_cluster = None
            await asyncio.sleep(0.001)
            if self.join_waiter_handle:
                self.logger.debug("%s canceling join_waiter task", self.get_my_uri())
                self.join_waiter_handle.cancel()
                self.join_waiter_handle = None
        if self.exit_waiter_handle:
            self.exiting_cluster = False
            await asyncio.sleep(0.001)
            self.exit_waiter_handle = None
        self.stopped = True
        
    async def stop_role(self):
        await self.role.stop()
        if self.role_async_handle:
            self.logger.debug("%s canceling scheduled task", self.get_my_uri())
            self.role_async_handle.cancel()
            self.role_async_handle = None

        
    # Called by Role
    async def record_message_problem(self, message, problem):
        if self.local_config.record_message_problems:
            rec = dict(problem=problem, message=message)
            self.message_problem_history.append(rec)
            
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
        if self.exiting_cluster:
            return
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

    # Called by Role
    async def send_response(self, message, response):
        self.logger.debug("Sending response type %s to %s", response.get_code(), response.receiver)
        encoded = json.dumps(message, default=lambda o:o.__dict__)
        encoded_reply = json.dumps(response, default=lambda o:o.__dict__)
        await self.pilot.send_response(response.receiver, encoded, encoded_reply)

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
    async def record_op_detail(self, op_detail):
        if op_detail in [str(OpDetail.sending_catchup), str(OpDetail.sending_backdown)]:
            if EventType.resync_op in self.event_control.active_events:
                await self.event_control.emit_resync_op(str(op_detail))
        elif EventType.election_op in self.event_control.active_events:
            await self.event_control.emit_election_op(str(op_detail))



