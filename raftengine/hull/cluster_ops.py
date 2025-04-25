import random
import logging
import json
from copy import deepcopy
from dataclasses import dataclass
from raftengine.api.log_api import LogRec, RecordCode
from raftengine.api.hull_api import HullAPI
from raftengine.api.log_api import LogAPI
from raftengine.messages.cluster_change import ChangeOp
from raftengine.api.types import ClusterConfig, NodeRec, ClusterSettings

@dataclass
class FollowerTracker:
    uri: str 
    nextIndex: int = 0
    lastSentIndex: int = 0
    matchIndex: int = 0
    msg_count: int = 0
    reply_count: int = 0
    last_msg_time: int = 0
    last_reply_time: int = 0

class ClusterOps:

    def __init__(self, hull:HullAPI, initial_config: ClusterConfig, log:LogAPI):
        self.hull = hull
        self.initial_config = initial_config
        self.logger = logging.getLogger("ClusterOps")
        self.follower_trackers = dict()
        self.current_config = None
        self.log = log
        self._leader_uri = None

    async def start(self):
        await self.get_cluster_config()

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
                                   use_dynamic_config=init.use_dynamic_config)
        cc = ClusterConfig(nodes=nd, settings=settings)
        res = await self.log.save_cluster_config(cc)
        self.current_config = res
        return res

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

    async def plan_add_node(self, node_uri):
        cc = await self.get_cluster_config()
        if cc.pending_node:
            return None
        if node_uri not in cc.nodes:
            new_cc = deepcopy(cc)
            rec = NodeRec(node_uri)
            rec.is_adding = True
            rec.is_loading = True
            new_cc.pending_node = rec
            return new_cc
        return None

    async def plan_remove_node(self, node_uri):
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
        cc = await self.get_cluster_config()
        if cc.pending_node:
            raise Exception(f"cluster memebership change already in progress with node {cc.pending_node.uri}")
        if node_uri not in cc.nodes:
            new_cc = await self.plan_add_node(node_uri)
            res = await self.log.save_cluster_config(new_cc)
            self.current_config = res
            return res
        raise Exception(f'node {node_uri} is already in active node set')

    async def node_add_prepared(self, node_uri):
        cc = await self.get_cluster_config()
        if cc.pending_node is None or cc.pending_node.uri != node_uri:
            raise Exception(f'node {node_uri} is not pending add')
        cc.pending_node.is_loading = False
        res = await self.log.save_cluster_config(cc)
        self.current_config = res
        return res
        
    async def finish_node_add(self, node_uri):
        cc = await self.get_cluster_config()
        if cc.pending_node is not None and cc.pending_node.uri == node_uri and cc.pending_node.is_adding:
            cc.pending_node.is_adding = False
            cc.nodes[node_uri] = cc.pending_node
            cc.pending_node = None
            res =  await self.log.save_cluster_config(cc)
            self.current_config = res
            return res
        raise Exception(f'node {node_uri} is not pending addition')

    async def start_node_remove(self, node_uri):
        cc = await self.get_cluster_config()
        if cc.pending_node:
            raise Exception(f"cannot remove node {node_uri}, another action is pending for node {cc.pending_node.uri}")
        if node_uri in cc.nodes:
            new_cc = await self.plan_remove_node(node_uri)
            res =  await self.log.save_cluster_config(new_cc)
            self.current_config = res
            return res
        raise Exception(f'node {node_uri} is not in active node set')

    async def finish_node_remove(self, node_uri):
        cc = await self.get_cluster_config()
        if cc.pending_node is not None and cc.pending_node.uri == node_uri and cc.pending_node.is_removing:
            cc.pending_node = None
            res =  await self.log.save_cluster_config(cc)
            self.current_config = res
            return res
        raise Exception(f'node {node_uri} is not pending removal')

    async def node_is_voter(self, node_uri):
        cc = await self.get_cluster_config()
        # leader gets the wrong answer here if itself is removing, so leader needs a different check
        if (cc.pending_node 
            and cc.pending_node.uri == node_uri
            and cc.pending_node.is_loading):
            return False
        return True
    
    async def handle_membership_change_log_update(self, log_rec):
        cdict = json.loads(log_rec.command)
        config = ClusterConfig(**cdict['config'])
        op = cdict['op']
        operand = cdict['operand']
        if op == "add_node":
            config = await self.start_node_add(operand)
        if op == "remove_node":
            config = await self.start_node_remove(operand)
        self.logger.debug(f"%s started op=%s operand=%s", self.my_uri(), op, operand)
        if operand == self.my_uri():
            self.logger.warning("%s calling stop on self", self.my_uri())
            await self.hull.exiting_cluster()
            return

    async def handle_membership_change_log_commit(self, log_rec):
        cdict = json.loads(log_rec.command)
        config = ClusterConfig(**cdict['config'])
        op = cdict['op']
        operand = cdict['operand']
        if op == "add_node":
            config = await self.finish_node_add(operand)
        if op == "remove_node":
            config = await self.finish_node_remove(operand)
        self.logger.debug(f"%s finished op=%s operand=%s", self.my_uri(), op, operand)
            
    async def do_node_inout(self, op, target_uri):
        command = None
        if op == ChangeOp.add:
            plan = await self.plan_add_node(target_uri)
            command = dict(op="add_node", config=plan, operand=target_uri)
        elif op == ChangeOp.remove:
            plan = await self.plan_remove_node(target_uri)
            command = dict(op="remove_node", config=plan, operand=target_uri)
        else:
            self.logger.error(f"got unknown op {op} trying to service membership change message")
            return False
        # gotta do the broadcast first, because applying it on remove means
        # that the target node is no longer in the list to receive broadcasts.
        # ask me how I know
        
        encoded = json.dumps(command, default=lambda o:o.__dict__)
        rec = LogRec(code=RecordCode.cluster_config, command=encoded)
        rec_to_send = await self.log.append(rec)
        await self.hull.role.broadcast_log_record(rec_to_send)
        if op == "ADD":
            await self.start_node_add(target_uri)
        else:
            await self.start_node_remove(target_uri)
        if target_uri == self.my_uri():
            self.hull.role.exit_in_progress = True
        return True

    async def finish_cluster_config(self, log_record):
        if log_record.applied:
            return
        cdict = json.loads(log_record.command)
        op = cdict['op']
        operand = cdict['operand']
        if op == "remove_node" and operand == self.my_uri():
            config = ClusterConfig(**cdict['config'])
            t_uri = list(config.nodes.keys())[0]
            await self.hull.role.transfer_power(t_uri, log_record)
            return
        if op == "add_node":
            await self.node_add_prepared(operand)
            await self.tracker_for_follower(operand)
        elif op == "remove_node":
            del self.follower_trackers[operand] 
        await self.handle_membership_change_log_commit(log_record)
        log_record.applied = True
        await self.log.replace(log_record)
        await self.hull.role.send_heartbeats()

    async def tracker_for_follower(self, uri):
        tracker = self.follower_trackers.get(uri, None)
        if not tracker:
            last_index = await self.log.get_last_index()
            tracker = FollowerTracker(uri=uri,
                                      nextIndex=last_index + 1,
                                      matchIndex=0)
            self.follower_trackers[uri] = tracker
        return tracker

    def get_all_follower_trackers(self):
        return list(self.follower_trackers.values())


    def my_uri(self):
        return self.hull.get_my_uri()
