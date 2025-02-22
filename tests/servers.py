import asyncio
import logging
import time
import pytest
import functools
import dataclasses
import traceback
import json
from pathlib import Path
from logging.config import dictConfig
from collections import defaultdict
from raftengine.api.log_api import LogRec
from raftengine.hull.hull_config import ClusterConfig, LocalConfig
from raftengine.hull.hull import Hull
from raftengine.messages.request_vote import RequestVoteMessage,RequestVoteResponseMessage
from raftengine.messages.append_entries import AppendEntriesMessage, AppendResponseMessage
from raftengine.messages.base_message import BaseMessage
from dev_tools.memory_log import MemoryLog
from dev_tools.sqlite_log import SqliteLog

from raftengine.api.pilot_api import PilotAPI

def setup_logging(additions=None):
    #lfstring = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    lfstring = '[%(levelname)s] %(name)s: %(message)s'
    log_formaters = dict(standard=dict(format=lfstring))
    logfile_path = Path('.', "test.log")
    if False:
        file_handler = dict(level="DEBUG",
                            formatter="standard",
                            encoding='utf-8',
                            mode='w',
                            filename=str(logfile_path))
        file_handler['class'] = "logging.FileHandler"
    stdout_handler =  dict(level="DEBUG",
                           formatter="standard",
                           stream="ext://sys.stdout")
    # can't us "class" in above form
    stdout_handler['class'] = "logging.StreamHandler"
    log_handlers = dict(stdout=stdout_handler)
    handler_names = ['stdout']
    if False:
        log_handlers = dict(file=file_handler, stdout=stdout_handler)
        handler_names = ['file', 'stdout']
    log_loggers = set_levels(handler_names, additions=additions)
    log_config = dict(version=1, disable_existing_loggers=False,
                      formatters=log_formaters,
                      handlers=log_handlers,
                      loggers=log_loggers)
        # apply the caller's modifications to the level specs
    try:
        dictConfig(log_config)
    except:
        from pprint import pprint
        pprint(log_config)
        raise
    return log_config

def set_levels(handler_names, additions=None):
    log_loggers = dict()
    err_log = dict(handlers=handler_names, level="ERROR", propagate=False)
    warn_log = dict(handlers=handler_names, level="WARNING", propagate=False)
    root_log = dict(handlers=handler_names, level="ERROR", propagate=False)
    info_log = dict(handlers=handler_names, level="INFO", propagate=False)
    debug_log = dict(handlers=handler_names, level="DEBUG", propagate=False)
    log_loggers[''] = root_log
    log_loggers['PausingServer'] = info_log
    default_log =  info_log
    #default_log =  debug_log
    log_loggers['Leader'] = default_log
    log_loggers['Follower'] = default_log
    log_loggers['Candidate'] = default_log
    log_loggers['BaseState'] = default_log
    log_loggers['Hull'] = default_log
    log_loggers['Substates'] = default_log
    log_loggers['SimulatedNetwork'] = default_log
    if additions:
        for add in additions:
            if add['level'] == "debug":
                log_loggers[add['name']] = debug_log
            elif add['level'] == "info":
                log_loggers[add['name']] = info_log
            elif add['level'] == "warn":
                log_loggers[add['name']] = warn_log
            elif add['level'] == "error":
                log_loggers[add['name']] = error_log
            else:
                raise Exception('Invalid level')
    return log_loggers

@pytest.fixture
async def cluster_maker():
    the_cluster = None

    def make_cluster(*args, **kwargs):
        nonlocal the_cluster
        the_cluster =  PausingCluster(*args, **kwargs)
        return the_cluster
    yield make_cluster
    if the_cluster is not None:
        await the_cluster.cleanup()
    
class simpleOps():
    total = 0
    explode = False
    exploded = False
    return_error = False
    reported_error = False
    async def process_command(self, command):
        logger = logging.getLogger("simpleOps")
        error = None
        result = None
        self.exploded = False
        op, operand = command.split()
        if self.explode:
            self.exploded = True
            raise Exception('boom!')
        if self.return_error:
            self.reported_error = True
            return None, "inserted error"
        if op not in ['add', 'sub']:
            error = "invalid command"
            logger.error("invalid command %s provided", op)
            return None, error
        if op == "add":
            self.total += int(operand)
        elif op == "sub":
            self.total -= int(operand)
        result = self.total
        logger.debug("command %s returning %s no error", command, result)
        return result, None


class PauseTrigger:

    async def is_tripped(self, server):
        return False

class WhenMessageOut(PauseTrigger):
    # When a particular message have been sent
    # by the raft code, and is waiting to be transported
    # to the receiver. You can just check the message
    # type, or require that type and a specific target receiver.
    # If you don't care about inspecting the message before it
    # is transported to the target server, leave the flush_when_done
    # flag set to True, otherwise set if false and then arrange for
    # transport after inspecting.
    def __init__(self, message_code, message_target=None, flush_when_done=True):
        self.message_code = message_code
        self.message_target = message_target
        self.flush_when_done = flush_when_done
        self.trigger_message = None

    def __repr__(self):
        msg = f"{self.__class__.__name__} {self.message_code} {self.message_target}"
        return msg

    async def is_tripped(self, server):
        done = False
        for message in server.out_messages:
            if message.get_code() == self.message_code:
                if self.message_target is None:
                    done = True
                elif self.message_target == message.receiver:
                    done = True
        if done:
            self.trigger_message = message
            if self.flush_when_done:
                await self.flush_one_out_message(server, message)  
        return done

    async def flush_one_out_message(self, server, message):
        if len(server.out_messages) == 0:
            return None
        if server.block_messages:
            return None
        new_list = []
        for msg in server.out_messages:
            if msg == message:
                server.logger.debug("FLUSH forwarding message %s", msg)
                await server.cluster.post_in_message(msg)
            else:
                new_list.append(msg)
        server.out_messages = new_list
        
class WhenCommitIndexSent(WhenMessageOut):

    def __init__(self, target_index, message_target=None):
        super().__init__(AppendEntriesMessage.get_code(), message_target, flush_when_done=True)
        self.target_index = target_index
        
    def __repr__(self):
        msg = super().__repr__()
        msg += f" index={self.target_index}"
        return msg

    async def is_tripped(self, server):
        done = await super().is_tripped(server)
        if done:
            if self.trigger_message.commitIndex == self.target_index:
                return done
        return False
    
class WhenMessageIn(PauseTrigger):
    # Whenn a particular message have been transported
    # from a different server and placed in the input
    # pending buffer of this server. The message
    # in question has not yet been delivered to the
    # raft code. You can just check the message
    # type, or require that type and a specific sender
    def __init__(self, message_code, message_sender=None):
        self.message_code = message_code
        self.message_sender = message_sender

    def __repr__(self):
        msg = f"{self.__class__.__name__} {self.message_code} {self.message_sender}"
        return msg
    
    async def is_tripped(self, server):
        done = False
        for message in server.in_messages:
            if message.get_code() == self.message_code:
                if self.message_sender is None:
                    done = True
                if self.message_sender == message.sender:
                    done = True
        return done
    
class WhenInMessageCount(PauseTrigger):
    # When a particular message has been transported
    # from a different server and placed in the input
    # pending buffer of this server a number of times.
    # Until the count is reached, messages will be processed,
    # then the last on will be held in the input queue.
    # If this is a problem follow the wait for this trigger
    # with server.do_next_in_msg()

    def __init__(self, message_code, goal):
        self.message_code = message_code
        self.goal = goal
        self.captured = []
        self.logged_done = False

    def __repr__(self):
        msg = f"{self.__class__.__name__} {self.message_code} {self.goal}"
        return msg
    
    async def is_tripped(self, server):
        logger = logging.getLogger("Triggers")
        for message in server.in_messages:
            if message.get_code() == self.message_code:
                if message not in self.captured:
                    self.captured.append(message)
                    logger.debug("%s captured = %s", self, self.captured)
        if len(self.captured) == self.goal:
            if not self.logged_done:
                logger.debug("%s satisfied ", self)
                self.logged_done = True
            return True
        else:
            return False
    
    
class WhenAllMessagesForwarded(PauseTrigger):
    # When the server has forwarded (i.e. transported) all
    # of its pending output messages to the other servers,
    # where they sit in the input queues.

    def __repr__(self):
        msg = f"{self.__class__.__name__}"
        return msg
    
    async def is_tripped(self, server):
        if len(server.out_messages) > 0:
            return False
        return True
    
class WhenAllInMessagesHandled(PauseTrigger):
    # When the server has processed all the messages
    # in the input queue, submitting them to the raft
    # code for processing.

    def __repr__(self):
        msg = f"{self.__class__.__name__}"
        return msg
    
    async def is_tripped(self, server):
        if len(server.in_messages) > 0:
            return False
        return True
    
class WhenIsLeader(PauseTrigger):
    # When the server has won the election and
    # knows it.
    def __repr__(self):
        msg = f"{self.__class__.__name__}"
        return msg
    
    async def is_tripped(self, server):
        if server.hull.get_state_code() == "LEADER":
            return True
        return False
    
class WhenHasLeader(PauseTrigger):
    # When the server started following specified leader
    def __init__(self, leader_uri):
        self.leader_uri = leader_uri

    def __repr__(self):
        msg = f"{self.__class__.__name__} leader={self.leader_uri}"
        return msg
        
    async def is_tripped(self, server):
        if server.hull.get_state_code() != "FOLLOWER":
            return False
        if server.hull.state.leader_uri == self.leader_uri:
            return True
        return False
    
class WhenHasLogIndex(PauseTrigger):
    # When the server has saved record with provided index
    def __init__(self, index):
        self.index = index

    def __repr__(self):
        msg = f"{self.__class__.__name__} index={self.index}"
        return msg
        
    async def is_tripped(self, server):
        if await server.hull.log.get_last_index() >= self.index:
            return True
        return False
    
class WhenHasCommitIndex(PauseTrigger):
    # When the server has committed record with provided index
    def __init__(self, index):
        self.index = index

    def __repr__(self):
        msg = f"{self.__class__.__name__} index={self.index}"
        return msg
        
    async def is_tripped(self, server):
        if await server.hull.log.get_local_commit_index() >= self.index:
            return True
        return False
    
class WhenElectionDone(PauseTrigger):
    # Examine whole cluster to make sure we are in the
    # post election quiet period

    def __init__(self, voters=None):
        self.announced = defaultdict(dict)
        self.voters = voters
        
    def __repr__(self):
        msg = f"{self.__class__.__name__}"
        return msg
        
    async def is_tripped(self, server):
        logger = logging.getLogger("Triggers")
        quiet = []
        have_leader = False
        if self.voters is None:
            self.voters = list(server.cluster.nodes.keys())
        for uri in self.voters:
            node = server.cluster.nodes[uri]
            if node.hull.get_state_code() == "LEADER":
                have_leader = True
                rec = self.announced[uri]
                if "is_leader" not in rec:
                    rec['is_leader'] = True
                    logger.debug('%s is now leader', uri)
            if len(node.in_messages) == 0 and len(node.out_messages) == 0:
                quiet.append(uri)
                rec = self.announced[uri]
                if "is_quiet" not in rec:
                    rec['is_quiet'] = True
                    logger.debug('%s is now quiet, total quiet == %d', uri, len(quiet))
        if have_leader and len(quiet) == len(self.voters):
            return True
        return False
    
class TriggerSet:

    def __init__(self, triggers=None, mode="and", name=None):
        if triggers is None:
            triggers = []
        self.triggers = triggers
        self.mode = mode
        if name is None:
            name = f"Set-[str(cond) for cond in triggers]"
        self.name = name

    def __repr__(self):
        return self.name

    def add_trigger(self, trigger):
        self.triggers.append(trigger)

    async def is_tripped(self, server):
        logger = logging.getLogger("Triggers")
        for_set = 0
        for cond in self.triggers:
            is_tripped = await cond.is_tripped(server)
            if not is_tripped:
                if self.mode == "and":
                    return False
            for_set += 1
            if self.mode == "or":
                logger.debug(f"%s Trigger {cond} tripped, run done (or)", server.uri)
                return True
            if for_set == len(self.triggers):
                logger.debug(f"%s Trigger {cond} tripped, all tripped", server.uri)
                return True
        return False

class TestHull(Hull):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.break_on_message_code = None
        self.explode_on_message_code = None
        self.corrupt_message_with_code = None
        self.state_run_later_def = None
        self.timers_paused = False
        self.condition = asyncio.Condition()
        self.logger = logging.getLogger("SimulatedNetwork")
        
    async def on_message(self, message):

        dmsg = self.decode_message(message)
        if self.break_on_message_code == dmsg.get_code():
            print('here to catch break')
        if self.explode_on_message_code == dmsg.get_code():
            result = await super().on_message('{"code":"foo"}')
        if self.corrupt_message_with_code == dmsg.get_code():
            dmsg.entries = [dict(a=1),]
            self.logger.error('%s corrupted message by inserting garbage as log rec', self.local_config.uri)
            result = await self.inner_on_message(dmsg)
        else:
            result = await super().on_message(message)
        return result

    async def pause_timers(self):
        self.timers.paused = True
            
    async def release_timers(self):
        async with self.condition:
            self.timers.paused = True
            await self.condition.notify()
            
    async def state_after_runner(self, target):
        while self.timers_paused:
            async with self.condition:
                await self.condition.wait()
        return await super().state_after_runner(target)

    async def state_run_after(self, delay, target):
        self.state_run_later_def = dict(state_code=self.state.state_code,
                                        delay=delay, target=target)
        await super().state_run_after(delay, target)

class Network:

    def __init__(self, name, nodes, net_mgr):
        self.name = name
        self.nodes = {}
        self.net_mgr = net_mgr
        self.logger = logging.getLogger("SimulatedNetwork")
        for uri,node in nodes.items():
            self.add_node(node)

    def __str__(self):
        return f"Net: {self.name} {len(self.nodes)} nodes"
    
    def add_node(self, node):
        if node.uri not in self.nodes:
            self.nodes[node.uri] = node
        node.change_networks(self)
        
    def remove_node(self, node):
        if node.uri in self.nodes:
            del self.nodes[node.uri]

    def get_node_by_uri(self, uri):
        if uri not in self.nodes:
            return None
        return self.nodes[uri]

    async def post_in_message(self, message):
        node = self.nodes[message.receiver]
        node.in_messages.append(message)
        
    async def deliver_all_pending(self, out_only=False):
        in_ledger = []
        out_ledger = []
        any = True
        count = 0
        # want to bounce around, not deliver each ts completely
        while any:
            any = False
            for uri, node in self.nodes.items():
                if len(node.in_messages) > 0 and not out_only:
                    msg = await node.do_next_in_msg()
                    if msg:
                        count += 1
                        in_ledger.append(msg)
                        any = True
                if len(node.out_messages) > 0:
                    msg = await node.do_next_out_msg()
                    if msg:
                        count += 1
                        out_ledger.append(msg)
                        any = True
        return dict(in_ledger=in_ledger, out_ledger=out_ledger, count=count)

    async def do_next_in_msg(self, node):
        if len(node.in_messages) == 0:
            return None
        msg = node.in_messages.pop(0)
        if node.block_messages:
            self.logger.info("------------ Network Simulation DROPPING (caching) incoming message %s", msg)
            node.blocked_in_messages.append(msg)
            return None
        self.logger.debug("%s handling message %s", node.uri, msg)
        await node.hull.on_message(json.dumps(msg, default=lambda o:o.__dict__))
        return msg
    
    async def do_next_out_msg(self, node):
        if len(node.out_messages) == 0:
            return None
        msg = node.out_messages.pop(0)
        if node.block_messages:
            self.logger.info("------------ Network Simulation DROPPING (caching) outgoing message %s", msg)
            node.blocked_out_messages.append(msg)
            return None
        target = self.get_node_by_uri(msg.receiver)
        if not target:
            self.logger.info("%s target is not on this network, loosing message %s", node.uri, msg)
            node.lost_out_messages.append(msg)
            return
        self.logger.debug("%s forwarding message %s", node.uri, msg)
        target.in_messages.append(msg)
        return msg
        

class NetManager:

    def __init__(self, all_nodes:dict, start_nodes:dict):
        self.all_nodes = all_nodes
        self.start_nodes = start_nodes
        self.full_cluster = None
        self.quorum_segment = None
        self.other_segments = None
        self.logger = logging.getLogger("SimulatedNetwork")

    def setup_network(self):
        self.full_cluster = Network("main", self.start_nodes, self)
        return self.full_cluster

    def get_majority_network(self):
        if self.quorum_segment:
            return self.quorum_segment
        return self.full_cluster
    
    def split_network(self, segments):
        # don't mess with original
        # validate first
        node_set = set()
        disp = []
        for part in segments:
            for uri,node in part.items():
                assert node.uri in self.full_cluster.nodes
                assert node not in node_set
                node_set.add(node)
        # all legal, no dups
        self.other_segments = []
        for part in segments:
            seg_len = len(part)
            if seg_len > len(self.full_cluster.nodes) / 2:
                net = Network("quorum", part, self)
                self.quorum_segment = net
            else:
                net_name = f"seg-{len(self.other_segments)}"
                net = Network(net_name, part, self)
                self.other_segments.append(net)
            disp.append(f"{net.name}:{len(net.nodes)}")
        self.logger.info(f"Split {len(self.full_cluster.nodes)} node network into seg lengths {','.join(disp)}")

    def unsplit(self):
        if self.other_segments is None:
            return
        for uri,node in self.full_cluster.nodes.items():
            self.full_cluster.add_node(node)
            node.hull.cluster_config.node_uris =  list(self.full_cluster.nodes.keys())
        self.quorum_segment = None
        self.other_segments = None

    async def post_in_message(self, message):
        if self.quorum_segment is None:
            await self.full_cluster.post_in_message(message)
            return
        if message.receiver in self.quorum_segment.nodes:
            await self.quorum_segment.post_in_message(message)
            return

    async def deliver_all_pending(self,  quorum_only=False, out_only=False):
        if self.quorum_segment is None:
            net1 = self.full_cluster
        else:
            net1 = self.quorum_segment
        first_res = await net1.deliver_all_pending(out_only=out_only)
        if self.quorum_segment is None or quorum_only:
            first_res['multiple_networks'] = False
            return first_res
        res = dict(multiple_networks=True, result_list=[first_res,])
        for net in self.other_segments:
            seg_res = await net.deliver_all_pending(out_only=out_only)
            res['result_list'].append(seg_res)
        return res

def setup_sqlite_log(uri):
    number = uri.split('/')[-1]
    path = Path('/tmp', f"pserver_{number}.sqlite")
    if path.exists():
        path.unlink()
    log = SqliteLog(path)
    log.start()
    return log
        
class PausingServer(PilotAPI):

    def __init__(self, uri, cluster, use_log=MemoryLog):
        self.uri = uri
        self.cluster = cluster
        self.cluster_config = None
        self.local_config = None
        self.hull = None
        self.in_messages = []
        self.out_messages = []
        self.lost_out_messages = []
        self.logger = logging.getLogger("PausingServer")
        if use_log == MemoryLog:
            self.log = MemoryLog()
        elif use_log == SqliteLog:
            self.log = setup_sqlite_log(uri)
        self.trigger_set = None
        self.trigger = None
        self.break_on_message_code = None
        self.network = None
        self.block_messages = False
        self.blocked_in_messages = None
        self.blocked_out_messages = None

    def set_configs(self, local_config, cluster_config):
        self.cluster_config = cluster_config
        self.local_config = local_config
        self.hull = TestHull(self.cluster_config, self.local_config, self)
        self.operations = simpleOps()

    # Part of PilotAPI
    def get_log(self):
        return self.log

    # Part of PilotAPI
    async def process_command(self, command):
        return await self.operations.process_command(command)
        
    async def send_message(self, target, in_msg):
        msg = self.hull.decode_message(in_msg)
        self.logger.debug("queueing out msg %s", msg)
        self.out_messages.append(msg) 

    # Part of PilotAPI
    async def send_response(self, target, in_msg, in_reply):
        reply = self.hull.decode_message(in_reply)
        self.logger.debug("queueing out reply %s", reply)
        self.out_messages.append(reply) 
        
    async def start(self):
        await self.hull.start()
        
    async def start_election(self):
        await self.hull.campaign()

    def change_networks(self, network):
        if self.network and self.network != network:
            self.logger.info("%s changing networks, must be partition or heal, new net %s", self.uri, str(network))
        self.network = network

    def block_network(self):
        self.blocked_in_messages = []
        self.blocked_out_messages = []
        self.block_messages = True
    
    def unblock_network(self, deliver=False):
        self.block_messages = False
        if not deliver:
            self.blocked_in_messages = None
            self.blocked_out_messages = None
            return
        for msg in self.blocked_in_messages:
            self.in_messages.append(msg)
        for msg in self.blocked_out_messages:
            self.out_messages.append(msg)

    async def accept_in_msg(self, message):
        # called by network on behalf of sender
        self.logger.debug("queueing sent %s", message)
        self.in_messages.append(message)
        
    async def do_next_in_msg(self):
        # sometimes test code wants to cycle individual servers specifically
        return await self.network.do_next_in_msg(self)
        
    async def do_next_out_msg(self):
        # sometimes test code wants to cycle individual servers specifically
        return await self.network.do_next_out_msg(self)

    async def do_next_msg(self):
        # called by network when running simulation
        msg = await self.do_next_out_msg()
        if not msg:
            msg = await self.do_next_in_msg()
        return msg

    def clear_out_msgs(self):
        # called by network when simulating network breaks and reconnects
        for msg in self.out_messages:
            self.logger.debug('%s clearing pending outbound %s', self.uri, msg)
        self.out_messages = []
        
    def clear_in_msgs(self):
        # called by network when simulating network breaks and reconnects
        for msg in self.in_messages:
            self.logger.debug('%s clearing pending inbound %s', self.uri, msg)
        self.in_messages = []
        
    def clear_all_msgs(self):
        # called by network when simulating network breaks and reconnects
        self.clear_out_msgs()
        self.clear_in_msgs()
        
    async def cleanup(self):
        hull = self.hull
        if hull.state:
            self.logger.debug('cleanup stopping %s %s', hull.state, hull.get_my_uri())
            handle =  hull.state_async_handle
            await hull.state.stop()
            if handle:
                self.logger.debug('after %s %s stop, handle.cancelled() says %s',
                                 hull.state, hull.get_my_uri(), handle.cancelled())
            
        self.hull = None
        del hull
        self.log.close()

    def clear_triggers(self):
        self.trigger = None
        self.trigger_set = None

    def set_trigger(self, trigger):
        if self.trigger is not None:
            raise Exception('this is for single trigger operation, already set')
        if self.trigger_set is not None:
            raise Exception('only one trigger mode allowed, already have single set')
        self.trigger = trigger
        
    def add_trigger(self, trigger):
        if self.trigger is not None:
            raise Exception('only one trigger mode allowed, already have single')
        if self.trigger_set is None:
            self.trigger_set = TriggerSet(mode="and")
        self.trigger_set.add_trigger(trigger)
        
    async def run_till_triggers(self, timeout=1, free_others=False):
        start_time = time.time()
        done = False
        while not done and time.time() - start_time < timeout:
            if self.trigger is not None:
                if await self.trigger.is_tripped(self):
                    self.logger.debug(f"%s Trigger {self.trigger} tripped, run done", self.uri)
                    done = True
                    break
            elif self.trigger_set is not None:
                if await self.trigger_set.is_tripped(self):
                    self.logger.debug(f"%s TriggerSet {self.trigger_set} tripped, run done", self.uri)
                    done = True
                    break
            if not done:
                msg = await self.network.do_next_out_msg(self)
                if not msg:
                    msg = await self.network.do_next_in_msg(self)
                omsg = False
                if free_others:
                    for uri, node in self.cluster.nodes.items():
                        omsg_tmp = await node.do_next_msg()
                        if omsg_tmp:
                            omsg = True
                if not msg and not omsg:
                    await asyncio.sleep(0.00001)
        if not done:
            raise Exception(f'{self.uri} timeout waiting for triggers')
        self.logger.info("-----!!!! PAUSE !!!!----- %s run_till_triggers complete, pausing", self.uri)
        return # all triggers tripped as required by mode flags, so pause ops
    
    async def dump_stats(self):
        if self.hull.state.state_code == "FOLLOWER":
            leaderId=self.hull.state.leader_uri
        else:
            leaderId=None
        stats = dict(uri=self.uri,
                     state_code=self.hull.state.state_code,
                     term=await self.log.get_term(),
                     prevLogIndex=await self.log.get_last_index(),
                     prevLogTerm=await self.log.get_last_term(),
                     leaderId=leaderId)
        return stats
                     

class PausingCluster:

    def __init__(self, node_count, use_log=MemoryLog):
        self.node_uris = []
        self.nodes = dict()
        self.logger = logging.getLogger("PausingCluster")
        self.auto_comms_flag = False
        self.async_handle = None
        for i in range(node_count):
            nid = i + 1
            uri = f"mcpy://{nid}"
            self.node_uris.append(uri)
            t1s = PausingServer(uri, self, use_log=use_log)
            self.nodes[uri] = t1s
        self.net_mgr = NetManager(self.nodes, self.nodes)
        net = self.net_mgr.setup_network()
        for uri, node in self.nodes.items():
            node.network = net
        assert len(self.node_uris) == node_count

    def build_cluster_config(self, heartbeat_period=1000,
                             leader_lost_timeout=1000,
                             election_timeout_min=10000,
                             election_timeout_max=20000):
        
            cc = ClusterConfig(node_uris=self.node_uris,
                               heartbeat_period=heartbeat_period,
                               leader_lost_timeout=leader_lost_timeout,
                               election_timeout_min=election_timeout_min,
                               election_timeout_max=election_timeout_max,)
            return cc

    def set_configs(self, cluster_config=None):
        if cluster_config is None:
            cluster_config = self.build_cluster_config()
        for uri, node in self.nodes.items():
            # in real code you'd have only on cluster config in
            # something like a cluster manager, but in test
            # code we sometimes want to change something
            # in it for only some of the servers, not all,
            # so each gets its own copy
            cc = dataclasses.replace(cluster_config)
                           
            local_config = LocalConfig(uri=uri,
                                       working_dir='/tmp/',
                                       )
            node.set_configs(local_config, cc)

    async def start(self, only_these=None):
        for uri, node in self.nodes.items():
            await node.start()

    def split_network(self, segments):
        self.net_mgr.split_network(segments)

    def unsplit(self):
        self.net_mgr.unsplit()

    async def run_sequence(self, sequence):
        await sequence.do_setup()
        # may raise timeout
        result = await sequence.wait_till_done()
        await sequence.do_teardown()
        return result
        
    async def post_in_message(self, message):
        # special situation, called when trigger trapped on out message,
        # but wants it to be delivered before pause
        await self.net_mgr.post_in_message(message)
        
    async def deliver_all_pending(self,  quorum_only=False, out_only=False):
        return await self.net_mgr.deliver_all_pending(quorum_only=quorum_only, out_only=out_only)

    async def auto_comms_runner(self):
        try:
            self.logger.error("-----------------------------auto_comms_runner starting")
            while self.auto_comms_flag:
                res = await self.deliver_all_pending()
                count = 0
                if res['multiple_networks']:
                    for subres in res['result_list']:
                        count += subres['count']
                else:
                    count = res['count']
                if count == 0:
                    await asyncio.sleep(0.00001)
            self.async_handle = None
            self.logger.error("-----------------------------auto_comms_runner exiting")
        except Exception as exc:
            self.logger.error("error trying to deliver messages %s", traceback.format_exc())
            
    async def start_auto_comms(self):
        if self.auto_comms_flag:
            return
        try:
            self.auto_comms_flag = True
            loop = asyncio.get_event_loop()
            self.async_handle = loop.call_soon(lambda: loop.create_task(self.auto_comms_runner()))
        except Exception as exc:
            self.logger.error("error trying to setup auto_comms runner %s", traceback.format_exc())
        
    async def stop_auto_comms(self):
        self.auto_comms_flag = False
        
    async def cleanup(self):
        self.logger.info("cleaning up cluster")
        if self.auto_comms_flag:
            await self.stop_auto_comms()
            await asyncio.sleep(0)
        for uri, node in self.nodes.items():
            await node.cleanup()
        # lose references to everything
        self.nodes = {}
        self.node_uris = []

class TimeoutTaskGroup(Exception):
    """Exception raised to terminate a task group due to timeout."""
        
class TestServerTimeout(Exception):
    """Exception raised because of unexpected timeout in running test server support code."""
        
class StdSequence:

    def __init__(self, cluster, name):
        self.name = name
        self.cluster = cluster

class SNormalElection(StdSequence):

    def __init__(self, cluster, timeout=1):
        super().__init__(cluster=cluster, name="NormalElection")
        self.timeout = timeout
        self.logger = logging.getLogger('PausingServer')
        self.done_count = 0
        self.expected_count = 0

    async def do_setup(self):
        for uri,node in self.cluster.nodes.items():
            node.clear_triggers()
            node.set_trigger(WhenElectionDone())
            self.expected_count += 1

    async def runner_wrapper(self, node):
        await node.run_till_triggers()
        self.done_count += 1
        
    async def wait_till_done(self):
        async def do_timeout(timeout):
            start_time = time.time()
            while self.done_count < self.expected_count:
                await asyncio.sleep(timeout/100.0)
            if time.time() - start_time >= timeout:
                raise TimeoutTaskGroup()
        try:
            async with asyncio.TaskGroup() as tg:
                for uri,node in self.cluster.nodes.items():
                    tg.create_task(self.runner_wrapper(node))
                    self.logger.debug('scheduled runner task for node %s in %s', node.uri, self.name)
                tg.create_task(do_timeout(self.timeout))
        except* TimeoutTaskGroup:
            raise TestServerTimeout('timeout on wait till done on %s!', self.name)
        
    async def do_teardown(self):
        for uri,node in self.cluster.nodes.items():
            node.clear_triggers()
            
class SNormalCommand(StdSequence):

    def __init__(self, cluster, command, timeout=1):
        super().__init__(cluster=cluster, name="NormalCommand")
        self.timeout = timeout
        self.command = command
        self.timeout = timeout
        self.logger = logging.getLogger('PausingServer')
        self.done_count = 0
        self.expected_count = 0
        self.restore_auto = False
        self.leader = None
        self.command_result = None
        self.target_index = None
        self.network = None

    async def do_setup(self):
        self.restore_auto = self.cluster.auto_comms_flag
        if self.cluster.auto_comms_flag:
            await self.cluster.stop_auto_comms()
        self.network = self.cluster.net_mgr.get_majority_network()
        for uri,node in self.network.nodes.items():
            node.clear_triggers()
            if node.hull.state.state_code == "LEADER":
                self.leader = node
                orig_index = await node.log.get_local_commit_index()
                self.target_index = orig_index + 1
                break
        for uri,node in self.network.nodes.items():
            trigger = WhenHasCommitIndex(self.target_index)
            self.logger.debug("set %s trigger for node %s", trigger, node)
            node.set_trigger(trigger)
            self.expected_count += 1
        self.logger.debug("Setup normal command sequence, will run command at %s", node.uri)
        
    async def runner_wrapper(self, node):
        # wait until has commit index
        await node.run_till_triggers()
        if node == self.leader:
            # also need to send heartbeats so others get the commit index update
            self.logger.debug("Leader %s commit to %d, triggering heartbeats", node.uri, self.target_index)
            node.clear_triggers()
            await node.hull.state.send_heartbeats()
            self.logger.debug("Heartbeats send triggered, waiting for heartbeats send to followers")
            node.set_trigger(WhenCommitIndexSent(self.target_index))
            # leader needs to send commit index to all other nodes, even
            # if they are blocked or partitioned away
            for i in  range(0, len(self.cluster.nodes) -1):
                await node.run_till_triggers()
        self.done_count += 1
        
    async def command_wrapper(self, node, command):
        self.logger.debug("Running command %s at  %s", command, node.uri)
        self.command_result = await node.hull.run_command(command, timeout=0.1)
        
    async def wait_till_done(self):
        async def do_timeout(timeout):
            start_time = time.time()
            while self.done_count < self.expected_count:
                await asyncio.sleep(timeout/100.0)
            if time.time() - start_time >= timeout:
                raise TimeoutTaskGroup()
        try:
            async with asyncio.TaskGroup() as tg:
                tg.create_task(self.command_wrapper(self.leader, self.command))
                for uri,node in self.network.nodes.items():
                    tg.create_task(self.runner_wrapper(node))
                    self.logger.debug('scheduled runner task for node %s in %s', node.uri, self.name)
                tg.create_task(do_timeout(self.timeout))
        except* TimeoutTaskGroup:
            raise TestServerTimeout('timeout on wait till done on %s!', self.name)
        return self.command_result
    
    async def do_teardown(self):
        for uri,node in self.network.nodes.items():
            node.clear_triggers()
            
        if self.restore_auto:
            await self.cluster.start_auto_comms()
