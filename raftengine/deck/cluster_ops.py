import random
import logging
import time
import json
import asyncio
from typing import Optional
from copy import deepcopy
from dataclasses import dataclass
from raftengine.api.log_api import LogRec, RecordCode
from raftengine.api.deck_api import DeckAPI
from raftengine.api.log_api import LogAPI
from raftengine.api.snapshot_api import SnapShot
from raftengine.messages.cluster_change import ChangeOp, MembershipChangeMessage
from raftengine.api.types import ClusterConfig, NodeRec, ClusterSettings

@dataclass
class SnapShotCursor:
    uri: str
    snapshot: SnapShot
    offset:int = 0
    done: bool = False
    
@dataclass
class FollowerTracker:
    uri: str 
    nextIndex: int = 0
    matchIndex: int = 0
    msg_count: int = 0
    reply_count: int = 0
    last_msg_time: float = 0.0
    last_reply_time: float = 0.0
    add_loading = False
    sending_snapshot: SnapShotCursor = None

@dataclass
class NewNodeLoad:
    uri: str
    start_time: float = 0.0
    first_round_max_index: int = 0
    prev_round_max_index: int = 0
    round_count: int = 1
    change_message: Optional[MembershipChangeMessage] = None
    
class ClusterOps:

    def __init__(self, deck:DeckAPI, initial_config: ClusterConfig, log:LogAPI):
        self.deck = deck
        self.initial_config = initial_config
        self.logger = logging.getLogger("ClusterOps")
        self.follower_trackers = dict()
        self.current_config = None
        self.log = log
        self._leader_uri = None
        self.loading_data = None
        self.loading_round_timer_handle = None
        self.remove_message:Optional[MembershipChangeMessage] = None

    @property
    def leader_uri(self):
        return self._leader_uri

    @leader_uri.setter    
    def leader_uri(self, uri):
        self._leader_uri = uri
        
    async def get_cluster_config(self):
        stored_config = await self.log.get_cluster_config()
        if stored_config:
            self.current_config = stored_config
            return stored_config
        nd = {}
        init = self.initial_config
        for uri in init.node_uris:
            nd[uri] = NodeRec(uri)
        settings = ClusterSettings(heartbeat_period=init.heartbeat_period,
                                   election_timeout_min=init.election_timeout_min,
                                   election_timeout_max=init.election_timeout_max,
                                   max_entries_per_message=init.max_entries_per_message,
                                   use_pre_vote=init.use_pre_vote,
                                   use_check_quorum=init.use_check_quorum,
                                   use_dynamic_config=init.use_dynamic_config,
                                   commands_idempotent=init.commands_idempotent)
        cc = ClusterConfig(nodes=nd, settings=settings)
        cc = await self.log.save_cluster_config(cc)
        self.current_config = cc
        return cc

    def get_cluster_node_ids(self):
        return list(self.current_config.nodes.keys())

    async def get_heartbeat_period(self):
        config = await self.get_cluster_config()
        return config.settings.heartbeat_period

    async def get_election_timeout(self):
        config = await self.get_cluster_config()
        emin = config.settings.election_timeout_min
        emax = config.settings.election_timeout_max
        res = random.uniform(emin, emax)
        return res

    async def get_election_timeout_range(self):
        config = await self.get_cluster_config()
        emin = config.settings.election_timeout_min
        emax =  config.settings.election_timeout_max
        return emin, emax

    async def get_max_entries_per_message(self):
        config = await self.get_cluster_config()
        return config.settings.max_entries_per_message

    async def do_node_inout(self, op, target_uri, leader, message=None):
        """
        Called by leader to start the process of adding or removing
        a node. This may be in response to a MembershipChangeMessage
        or to a indirect call via the DeckAPI.
        """
        command = None
        if op == ChangeOp.remove:
            plan = await self.plan_remove_node(target_uri)
            command = dict(op="remove_node", config=plan, operand=target_uri)
            # Do the broadcast first, because applying it on remove means
            # that the target node is no longer in the list to receive broadcasts.
            # Ask me how I know
            encoded = json.dumps(command, default=lambda o:o.__dict__)
            rec = LogRec(code=RecordCode.cluster_config, command=encoded, term=await self.log.get_term())
            rec_to_send = await self.log.append(rec)
            self.logger.info("%s broadcasting remove for node %s", self.my_uri(), target_uri)
            await leader.broadcast_log_record(rec_to_send)
            await self.start_node_remove(target_uri)
            if message:
                self.remove_message = message
        elif op == ChangeOp.add:
            await self.start_node_add(target_uri) 
            # we need to start the catchup for this node
            tracker = await self.tracker_for_follower(target_uri)
            self.loading_data = NewNodeLoad(uri=target_uri,
                                            start_time=time.time(),
                                            first_round_max_index=await self.log.get_last_index(),
                                            change_message=message)
            tracker.add_loading = True
            self.logger.info("%s sending heartbeat to node %s to start pre-add catchup",
                             self.my_uri(), target_uri)
            await leader.send_heartbeats(target_only=message.target_uri)
        if target_uri == self.my_uri():
            leader.exit_in_progress = True

    async def do_update_settings(self, settings, leader):
        stored_config = await self.log.get_cluster_config()
        stored_config.settings = settings
        command = dict(op="update_settings", config=stored_config, operand="")
        encoded = json.dumps(command, default=lambda o:o.__dict__)
        rec = LogRec(code=RecordCode.cluster_config, command=encoded, term=await self.log.get_term())
        rec_to_send = await self.log.append(rec)
        await leader.broadcast_log_record(rec_to_send)
        
    async def get_cluster_config_json_string(self):
        cc = await self.get_cluster_config()
        encoded = json.dumps(cc, default=lambda o:o.__dict__)
        return encoded
        
    async def update_cluster_config_from_json_string(self, jsonstring):
        data = json.loads(jsonstring)
        csets = ClusterSettings(**data['settings'])
        newcc = ClusterConfig(settings=csets)
        nodes = {}
        for nrd in data['nodes'].values():
            nr = NodeRec(**nrd)
            newcc.nodes[nr.uri] = nr
        # Since this should only be called because the data showed up in a term
        # start log record (and the first one actually), then we are not
        # expecting it to have a pending membership change value. Not sure
        # what we could do in that case, if it is even possible
        await self.log.save_cluster_config(newcc)
        
    async def loading_round_timeout(self, target_uri, leader):
        self.logger.warning("%s loading records into new server %s is is too slow, aborting", self.my_uri(),
                            target_uri)
        await self.abort_node_add(target_uri, leader)
        
    async def start_loading_round_timer(self, target_uri, leader):
        config = await self.get_cluster_config()
        timeout =  config.settings.election_timeout_max
        loop = asyncio.get_event_loop()
        self.loading_round_timer_handle = loop.call_later(timeout,
                                                          lambda target_uri=target_uri, leader=leader:
                                                          asyncio.create_task(self.loading_round_timeout(target_uri, leader)))
        
    async def stop_loading_round_timer(self):
        if self.loading_round_timer_handle:
            self.loading_round_timer_handle.cancel()

    async def note_loading_progress(self, target_uri, log_index, leader):
        my_index = await self.log.get_last_index()
        self.logger.info("%s initial load to new server %s has reached %d of %d on round %d", self.my_uri(),
                         target_uri, log_index, my_index, self.loading_data.round_count)


        cc = await self.get_cluster_config()
        
        if log_index == my_index:
            self.logger.info("%s initial load to new server %s is complete," +
                             " logging membership change and replicating", self.my_uri(),
                             target_uri)
            await self.stop_loading_round_timer()
            tracker = await self.tracker_for_follower(target_uri)
            tracker.add_loading = False
            plan = await self.get_cluster_config() # current config include change info as pending_node field
            command = dict(op="add_node", config=plan, operand=target_uri)
            encoded = json.dumps(command, default=lambda o:o.__dict__)
            #print(f'\n\n\n{json.dumps(command, default=lambda o:o.__dict__, indent=4)}\n\n\n')
            rec = LogRec(code=RecordCode.cluster_config, command=encoded, term=await self.log.get_term())
            rec_to_send = await self.log.append(rec)
            await leader.broadcast_log_record(rec_to_send)
            msg = self.loading_data.change_message
            if msg:
                await leader.send_membership_change_response_message(msg, ok=True)
            #await self.deck.note_join_done(True)
            self.loading_data = None
            return True
        config = await self.get_cluster_config()
        timeout =  config.settings.election_timeout_max
        my_last = await self.log.get_last_index()
        if self.loading_data.round_count == 1:
            # we are still sending data in first round, see if we are done with it
            if log_index < self.loading_data.first_round_max_index:
                self.logger.debug("%s round 1 continues", self.my_uri())
                return True
            # finished with first round
            # start another round
            self.loading_data.round_count += 1
            self.loading_data.prev_round_max_index = my_last
            await self.start_loading_round_timer(target_uri, leader)
            return True
        # First round is finished, we are in some later round see if we are done
        if log_index >=  self.loading_data.prev_round_max_index:
            # finished with this round
            if self.loading_data.round_count == 10:
                # not finished after 10 rounds, time to abort
                self.logger.warning("%s initial load to new server %s is is too slow, 10 rounds done, aborting", self.my_uri(),
                                    target_uri)
                await self.abort_node_add(target_uri, leader)
                return False
            self.loading_data.round_count += 1
            self.loading_data.prev_round_max_index = my_last
            await self.start_loading_round_timer(target_uri, leader)
            self.logger.debug("%s round %d begins", self.my_uri(), self.loading_data.round_count)
            return True
        else:
            self.logger.debug("%s round %d continues", self.my_uri(), self.loading_data.round_count)
            return True
        
    async def abort_node_add(self, node_uri, leader):
        self.logger.debug("%s aborting add of node %s", self.my_uri(), node_uri)
        cc = await self.get_cluster_config()
        cc.pending_node = None
        await self.log.save_cluster_config(cc)
        await self.stop_loading_round_timer()
        del self.follower_trackers[node_uri]
        msg = self.loading_data.change_message
        if msg:
            await leader.send_membership_change_response_message(msg, ok=False)
        
    async def plan_add_node(self, node_uri):
        """
        Create a modified version of the cluster config that
        includes the pending change to add the named node.
        There is a pending_node property in the cluster config
        object that stores the new node.
        Leaders keep the config this state until they have brought
        the new node up to date and are ready to commit the
        change through log replication. At this point they
        save the change in the log and replicate it, and also
        begin to include the new node in replication.
        Followers stay in this state until they get a commit
        update from the leader, but they treat the new server as being
        part of the cluster as soon as they have saved
        the change in the log, not waiting for commit.
        Once the commit applies, they update the actual stored
        configuration to include the new node. This allows
        them to roll back the change should the uncommitted
        log record get removed after leadership change.
        """
        cc = await self.get_cluster_config()
        if cc.pending_node:
            return None
        if node_uri not in cc.nodes:
            new_cc = deepcopy(cc)
            rec = NodeRec(node_uri)
            new_cc.pending_node = rec
            rec.is_adding = True
            return new_cc
        return None

    async def plan_remove_node(self, node_uri):
        """
        Create a modified version of the cluster config that
        includes the pending change to remove the named node.
        There is a pending_node property in the cluster config
        object that stores the new exiting until the server is
        ready to commit the change, at which time the mode. The
        exiting node is not counted in votes, and it is not
        included in broadcasts. It simply waits for config
        changing log record to be committed and it then exits.
        If the log record is re-written on leadership change
        because it is uncommitted and not in the leader's
        log, then the config change will be reversed and the
        exiting node will continue as part of the cluster.
        """
        cc = await self.get_cluster_config()
        if cc.pending_node:
            return None
        if node_uri in cc.nodes:
            new_cc = deepcopy(cc)
            rec = new_cc.nodes[node_uri]
            rec.is_removing = True
            new_cc.pending_node = rec
            del new_cc.nodes[node_uri]
            return new_cc
        return None
        
    async def start_node_add(self, node_uri):
        """
        Update the stored config to include the change
        needed to add the named node to the cluster. If
        the calling node is the Leader, setup the process
        of loading the new node's log.
        This pending change is active, but not permanent. If a leadership
        change happens before the related log record is committed,
        then it is possible that the log record will be overwritten.
        In that case this change will be reversed
        """
        cc = await self.get_cluster_config()
        if cc.pending_node:
            raise Exception(f"cluster memebership change already in progress with node {cc.pending_node.uri}")
        if node_uri not in cc.nodes:
            new_cc = await self.plan_add_node(node_uri)
            res = await self.log.save_cluster_config(new_cc)
            self.current_config = res
            self.logger.debug("%s started add of node %s", self.my_uri(), node_uri)
            return res
        raise Exception(f'node {node_uri} is already in active node set')
        
    async def finish_node_add(self, node_uri):
        """
        Update the stored config to incororate the added node and discard
        the change in progress state. This means that the related log
        record has been committed at this node.
        """
        cc = await self.get_cluster_config()
        if cc.pending_node is not None and cc.pending_node.uri == node_uri:
            cc.pending_node.is_adding = False
            cc.nodes[node_uri] = cc.pending_node
            cc.pending_node = None
            res = await self.log.save_cluster_config(cc)
            self.current_config = res
            self.logger.debug("%s finished add of node %s", self.my_uri(), node_uri)
            return res
        raise Exception(f'node {node_uri} is not pending addition')

    async def start_node_remove(self, node_uri):
        """
        Update the stored config to include the change  needed to
        remove the named node to the cluster. 
        This pending change is active, but not permanent. If a leadership
        change happens before the related log record is committed,
        then it is possible that the log record will be overwritten.
        In that case this change will be reversed.
        """
        cc = await self.get_cluster_config()
        if cc.pending_node:
            raise Exception(f"cannot remove node {node_uri}, another action is pending for node {cc.pending_node.uri}")
        if node_uri in cc.nodes:
            new_cc = await self.plan_remove_node(node_uri)
            res =  await self.log.save_cluster_config(new_cc)
            self.current_config = res
            self.logger.debug("%s started remove of node %s", self.my_uri(), node_uri)
            return res
        raise Exception(f'node {node_uri} is not in active node set')

    async def finish_node_remove(self, node_uri):
        """
        Update the stored config to discard the change in progress
        state, leaving the node list without the removed node.
        This means that the related log record has been committed at
        this node and the change should no longer be reversed.
        """
        cc = await self.get_cluster_config()
        if cc.pending_node is not None and cc.pending_node.uri == node_uri and cc.pending_node.is_removing:
            cc.pending_node = None
            res =  await self.log.save_cluster_config(cc)
            self.current_config = res
            self.logger.debug("%s finished remove of node %s", self.my_uri(), node_uri)
            return res
        raise Exception(f'node {node_uri} is not pending removal')

    async def reverse_config_change(self, log_rec):
        """
        When a cluster config change is discarded because if an
        log record overwrite after a leadership change, sending
        the log record to this method will undo the active but
        not permanent change, reverting the membership to the
        state prior to the change.
        """
        cc = await self.get_cluster_config()
        cdict = json.loads(log_rec.command)
        config = ClusterConfig(**cdict['config'])
        op = cdict['op']
        operand = cdict['operand']
        if op == "remove_node" and cc.pending_node and cc.pending_node.uri == operand:
            cc.nodes[operand] = cc.pending_node
            cc.pending_node.is_removing = False
            if operand == self.my_uri():
                await self.deck.note_exit_done(success=False)
        cc.pending_node = None
        return await self.log.save_cluster_config(cc)
    
    async def handle_membership_change_log_update(self, log_rec):
        """
        Called by followers to apply the membership change and
        make it active, but not permanent.
        Called when the related log record has arrived from the leader.
        """
        cdict = json.loads(log_rec.command)
        config = ClusterConfig(**cdict['config'])
        op = cdict['op']
        operand = cdict['operand']
        if op == "add_node":
            config = await self.start_node_add(operand)
        elif op == "remove_node":
            config = await self.start_node_remove(operand)
        elif op == "update_settings":
            pass
            
        self.logger.info(f"%s started op=%s operand=%s", self.my_uri(), op, operand)

    async def handle_membership_change_log_commit(self, log_rec):
        """
        Called by followers to make the membership change permanent.
        Called when the related log record is committed.
        """
        cdict = json.loads(log_rec.command)
        config = ClusterConfig(**cdict['config'])
        op = cdict['op']
        operand = cdict['operand']
        self.logger.info(f"%s got commit log rec for op=%s operand=%s", self.my_uri(), op, operand)
        if op == "add_node":
            # leader committed record, means that the node is loaded and ready
            # to vote
            if operand == self.my_uri():
                # when a node adds itself, it gets a reply to the
                # membership add node request, and on that reply
                # it updates the cluster config. Trying to do
                # it again will raise an error
                cc = await self.get_cluster_config()
                if not cc.pending_node:
                    return
            config = await self.finish_node_add(operand)
        elif op == "remove_node":
            config = await self.finish_node_remove(operand)
            if operand == self.my_uri():
                self.logger.warning("%s calling stop on self", self.my_uri())
                await self.deck.note_exit_done(success=True)
        elif op == "update_settings":
            stored_config = await self.log.get_cluster_config()
            stored_config.settings = ClusterSettings(**cdict['config']['settings'])
            res = await self.log.save_cluster_config(stored_config)
            self.current_config = res
        self.logger.info(f"%s finished op=%s operand=%s", self.my_uri(), op, operand)
            
    async def cluster_config_vote_passed(self, log_record, leader):
        """
        Called by leader when it receives enough votes on the membership
        change to commit it.
        """
        cdict = json.loads(log_record.command)
        op = cdict['op']
        operand = cdict['operand']
        await self.log.mark_applied(log_record.index)
        if op == "remove_node":
            self.logger.info(f"%s vote passed on op=%s operand=%s", self.my_uri(), op, operand)
            if operand != self.my_uri():
                await self.finish_node_remove(operand)
                self.logger.info(f"%s finished op=%s operand=%s", self.my_uri(), op, operand)
                # notify the target node directly
                await self.deck.role.send_heartbeats(target_only=operand)
                # notify everone else
                await self.deck.role.send_heartbeats()
                if self.remove_message:
                    await leader.send_membership_change_response_message(self.remove_message, ok=True)
                    self.remove_message = None
            else:
                config = ClusterConfig(**cdict['config'])
                t_uri = list(config.nodes.keys())[0]
                # we send the cluster config change log_record along to
                # transfer_power so that it will exit once the transfer is complete
                await self.deck.role.transfer_power(t_uri, log_record)
                return
        elif op == "add_node":
            await self.finish_node_add(operand)
        elif op == "update_settings":
            stored_config = await self.log.get_cluster_config()
            stored_config.settings = ClusterSettings(**cdict['config']['settings'])
            res = await self.log.save_cluster_config(stored_config)
            self.current_config = res

    async def tracker_for_follower(self, uri):
        tracker = self.follower_trackers.get(uri, None)
        if not tracker:
            last_index = await self.log.get_last_index()
            tracker = FollowerTracker(uri=uri,
                                      nextIndex=last_index + 1,
                                      matchIndex=0)
            self.follower_trackers[uri] = tracker
        return tracker

    def my_uri(self):
        return self.deck.get_my_uri()
