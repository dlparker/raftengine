import asyncio
import logging
import time
import os
import dataclasses
from dataclasses import dataclass
import traceback
from copy import deepcopy
from enum import Enum
import json
from pathlib import Path
from typing import Optional
from logging.config import dictConfig
from collections import defaultdict
import pytest

from raftengine.api.hull_config import ClusterConfig, LocalConfig
from raftengine.api.log_api import LogRec
from raftengine.hull.hull import Hull
from raftengine.messages.append_entries import AppendEntriesMessage
from raftengine.messages.base_message import BaseMessage
from dev_tools.memory_log import MemoryLog
from dev_tools.sqlite_log import SqliteLog

from raftengine.api.pilot_api import PilotAPI
log_config = None

trace_to_csv = False
digest_org = True
digest_csv = False

def get_current_test():
    full_name = os.environ.get('PYTEST_CURRENT_TEST').split(' ')[0]
    test_file = full_name.split("::")[0].split('/')[-1].split('.py')[0]
    test_name = full_name.split("::")[1]

    return full_name, test_file, test_name

def setup_logging(additions=None, default_level="error"): # pragma: no cover
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
    log_loggers = set_levels(handler_names, additions=additions, default_level=default_level)
    global log_config
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

def set_levels(handler_names, additions=None, default_level='error'): # pragma: no cover
    log_loggers = dict()
    err_log = dict(handlers=handler_names, level="ERROR", propagate=False)
    warn_log = dict(handlers=handler_names, level="WARNING", propagate=False)
    root_log = dict(handlers=handler_names, level="ERROR", propagate=False)
    info_log = dict(handlers=handler_names, level="INFO", propagate=False)
    debug_log = dict(handlers=handler_names, level="DEBUG", propagate=False)
    log_loggers[''] = root_log
    default_log = err_log
    if default_level == "warn":
        default_log =  warn_log
    elif default_level == "info":
        default_log =  info_log
    elif default_level == "debug":
        default_log =  debug_log
    log_loggers['Leader'] = default_log
    log_loggers['Follower'] = default_log
    log_loggers['Candidate'] = default_log
    log_loggers['BaseState'] = default_log
    log_loggers['Hull'] = default_log
    log_loggers['Substates'] = default_log
    log_loggers['PausingServer'] = default_log
    log_loggers['SimulatedNetwork'] = default_log
    log_loggers['test_code'] = default_log
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
        await the_cluster.stop_auto_comms()
        if trace_to_csv or digest_org or digest_csv:
            full_name, tfile, test_name = get_current_test()
            # convert the full name to something that doesn't look like a file path
            x = full_name.split('::')
            x = '_'.join(x)
            x = x.split('/')
            x = '_'.join(x)
            x = x.split('.py')
            x = '_'.join(x)
            fstem = x
            trace_dir = Path(Path(__file__).parent.parent.resolve(), "state_traces")
            if not trace_dir.exists():
                trace_dir.mkdir()
        if trace_to_csv:
            csvname = fstem + ".csv"
            full_trace_dir = Path(trace_dir, "full_csv")
            if not full_trace_dir.exists():
                full_trace_dir.mkdir()
            fpath = Path(full_trace_dir, csvname)
            csv_lines = the_cluster.test_trace.to_csv()
            with open(fpath, 'w') as f:
                for line in csv_lines:
                    outline = ','.join(line)
                    f.write(outline + "\n")
        if digest_org or digest_csv:
            org_lines = the_cluster.test_trace.to_condensed_org()
        if digest_org:
            orgname = fstem + ".org"
            org_dir = Path(trace_dir, "org_digest")
            if not org_dir.exists():
                org_dir.mkdir()
            fpath = Path(org_dir, orgname)
            if len(org_lines) > 0:
                with open(fpath, 'w') as f:
                    for line in org_lines:
                        f.write(line + "\n")
        if digest_csv:
            csv_digest_name = fstem + ".csv"
            csv_digest_dir = Path(trace_dir, "csv_digest")
            if not csv_digest_dir.exists():
                csv_digest_dir.mkdir()
            fpath = Path(csv_digest_dir, csv_digest_name)
            if len(org_lines) > 0:
                with open(fpath, 'w') as f:
                    for line in org_lines:
                        tmp = line.strip("|").split("|")
                        # this test is pretty fuzzy might fail, but
                        # it is hard to know how many columns there are
                        if len(tmp) < 10:
                            continue
                        new_line = ",".join(tmp)
                        f.write(new_line + "\n")
            
        
        await the_cluster.cleanup()
    
class SimpleOps(): # pragma: no cover
    total = 0
    explode = False
    exploded = False
    return_error = False
    reported_error = False
    async def process_command(self, command, serial):
        logger = logging.getLogger("SimpleOps")
        error = None
        result = None
        self.exploded = False
        op, operand = command.split()
        if self.explode:
            #await asyncio.sleep(0.1)
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


class PauseTrigger: # pragma: no cover

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
        msg = f"{self.__class__.__name__} {self.message_code}"
        if self.message_target:
            msg += f"target={self.message_target}"
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
        new_list = None
        if not server.block_messages:
            for msg in server.out_messages:
                if new_list is None:
                    new_list = []
                if msg == message:
                    server.logger.debug("FLUSH forwarding message %s", msg)
                    await server.cluster.post_in_message(msg)
                else:
                    new_list.append(msg)
        if new_list is not None:
            server.out_messages = new_list
        return new_list
        
class WhenCommitIndexSent(WhenMessageOut):

    def __init__(self, target_index, message_target=None):
        super().__init__(AppendEntriesMessage.get_code(), message_target, flush_when_done=True)
        self.target_index = target_index
        
    def __repr__(self):
        msg = super().__repr__()
        msg += f" index={self.target_index}"
        return msg

    async def is_tripped(self, server):
        done = False
        if await super().is_tripped(server):
            if self.trigger_message.commitIndex == self.target_index:
                done = True
        return done
    
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
        if await server.hull.log.get_commit_index() >= self.index:
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
            bits = ' '.join([str(cond) for cond in triggers])
            name = f"Set-{bits}"
        self.name = name

    def __repr__(self):
        bits = ' '.join([str(cond) for cond in self.triggers])
        name = f"Set-{bits}"
        return name

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
        self.timers_disabled = False
        self.wrapper_logger = logging.getLogger("SimulatedNetwork")
        
    async def on_message(self, message):
        dmsg = self.decode_message(message)
        if self.break_on_message_code == dmsg.get_code():
            print('here to catch break')
        if self.explode_on_message_code == dmsg.get_code():
            result = await super().on_message('{"code":"foo"}')
        if self.corrupt_message_with_code == dmsg.get_code():
            dmsg.entries = [dict(a=1),]
            self.wrapper_logger.error('%s corrupted message by inserting garbage as log rec', self.local_config.uri)
            result = await self.inner_on_message(dmsg)
        else:
            result = await super().on_message(message)
        return result

    async def state_run_after(self, delay, target):
        self.state_run_later_def = dict(state_code=self.state.state_code,
                                        delay=delay, target=target)
        if not self.timers_disabled:
            await super().state_run_after(delay, target)

    async def disable_timers(self):
        self.timers_disabled = True
        self.state_async_handle.cancel()
        self.state_async_handle = None
    
    async def enable_timers(self, reset=True):
        if reset:
            if self.state.state_code == "FOLLOWER":
                self.last_leader_contact = time.time()
            elif self.state.state_code == "LEADER":
                self.last_broadcast_time = time.time()
        if self.state_run_later_def:
            await super().state_run_after(self.state_run_later_def['delay'],
                                          self.state_run_later_def['target'])
        self.timers_disabled = False
            
    
class Network:

    def __init__(self, name, nodes, net_mgr):
        self.name = name
        self.nodes = {}
        self.net_mgr = net_mgr
        self.test_trace = None
        self.logger = logging.getLogger("SimulatedNetwork")
        for uri,node in nodes.items():
            self.add_node(node)

    def __str__(self):
        return f"Net: {self.name} {len(self.nodes)} nodes"
    
    def set_test_trace(self, test_trace):
        self.test_trace = test_trace
        
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
        if node.block_messages:
            self.logger.debug("Blocking in message %s", message)
            node.blocked_in_messages.append(message)
            await self.test_trace.note_blocked_message(node, message)
        else:
            node.in_messages.append(message)
            await self.test_trace.note_queued_in_message(node, message)
        
    async def deliver_all_pending(self, out_only=False):
        """ This does the final part of the work for the Cluster "mamual" 
        message delivery control mechanism by finding and moving
        pending messages from one server's output list to another 
        servers input list and triggering the target server to process
        the message. It continues this process until there are no more
        messages pending delivery.
        If the caller specifies out_only == True, then the process 
        will only move messages from out to in buffers, not trigger the
        input processing. This can be useful if a test wants to have
        granular control of the processing of the input messages.
        """
        in_ledger = []
        out_ledger = []
        any = True
        count = 0
        # want to bounce around, not deliver each ts completely
        while any:
            any = False
            for uri, node in self.nodes.items():
                node.am_paused = False
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
        for node in self.nodes.values():
            node.am_paused = True
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
        await self.test_trace.note_message_handled(node, msg)
        start_state = node.hull.state.state_code
        await node.on_message(json.dumps(msg, default=lambda o:o.__dict__))
        if start_state != node.hull.state.state_code:
            await self.test_trace.note_role_changed(node)
        return msg
    
    async def do_next_out_msg(self, node):
        if len(node.out_messages) == 0:
            return None
        msg = node.out_messages.pop(0)
        if node.block_messages:
            self.logger.info("------------ Network Simulation DROPPING (caching) outgoing message %s", msg)
            node.blocked_out_messages.append(msg)
            await self.test_trace.note_blocked_send(node, msg)
            return None
        target = self.get_node_by_uri(msg.receiver)
        if not target:
            self.logger.info("%s target is not on this network, loosing message %s", node.uri, msg)
            node.lost_out_messages.append(msg)
            await self.test_trace.note_lost_send(node, msg)
            return
        self.logger.debug("%s forwarding message %s", node.uri, msg)
        await self.test_trace.note_message_sent(node, msg)
        await self.post_in_message(msg)
        return msg
        
    def isolate_server(self, node):
        node.block_network()

    def reconnect_server(self, node, deliver=False):
        node.unblock_network(deliver=deliver)
        
class NetManager:

    def __init__(self, all_nodes:dict, start_nodes:dict):
        self.all_nodes = all_nodes
        self.start_nodes = start_nodes
        self.full_cluster = None
        self.quorum_segment = None
        self.other_segments = None
        self.test_trace = None
        self.logger = logging.getLogger("SimulatedNetwork")

    def setup_network(self):
        self.full_cluster = Network("main", self.start_nodes, self)
        self.full_cluster.set_test_trace(self.test_trace)
        return self.full_cluster

    def set_test_trace(self, test_trace):
        self.test_trace = test_trace
        if self.full_cluster:
            self.full_cluster.set_test_trace(test_trace)
        if self.quorum_segment:
            self.quorum_segment.set_test_trace(test_trace)
            for seg in self.other_segments:
                seg.set_test_trace(test_trace)
        
    def get_majority_network(self):
        if self.quorum_segment:
            return self.quorum_segment
        return self.full_cluster
    
    def get_minority_networks(self):
        return self.other_segments
    
    async def split_network(self, segments):
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
                net.set_test_trace(self.test_trace)
            else:
                net_name = f"seg-{len(self.other_segments)}"
                net = Network(net_name, part, self)
                self.other_segments.append(net)
                net.set_test_trace(self.test_trace)
                for node in part.values():
                    await self.test_trace.note_partition(node)
            disp.append(f"{net.name}:{len(net.nodes)}")
        self.logger.info(f"Split {len(self.full_cluster.nodes)} node network into seg lengths {','.join(disp)}")

    async def unsplit(self):
        if self.other_segments is None:
            return
        # this process is touchy because of the call to
        # test_trace.note_heal in the middle. The
        # call checks to see if the node is on the quorum
        # network, which effectively means we could mess
        # it up doing simple things here.
        for uri,node in self.full_cluster.nodes.items():
            cur_net = node.network
            cur_net.remove_node(node)
            self.full_cluster.add_node(node)
            if cur_net != self.quorum_segment:
                await self.test_trace.note_heal(node)
        self.quorum_segment = None
        self.other_segments = None

    async def post_in_message(self, message):
        if self.quorum_segment is None:
            await self.full_cluster.post_in_message(message)
            return
        partitions = [self.quorum_segment] + self.other_segments
        for partition in partitions:
            if message.receiver in partition.nodes and message.sender in partition.nodes:
                await partition.post_in_message(message)
                return

    async def deliver_all_pending(self,  quorum_only=False, out_only=False):
        """ This does the first part of the work for the Cluster "mamual" 
        message delivery control mechanism, by deciding which part of the 
        current network simulation should participate. If the network has
        been split, the test code may want only the partition containing 
        the majority of the nodes, the quorom segment, to participate in 
        the message flow. This layer chooses one or more network segments 
        and then lets the netwok simulation itself decide the 
        deliver details.
        If the caller specifies out_only == True, then the process 
        will only move messages from out to in buffers, not trigger the
        input processing. This can be useful if a test wants to have
        granular control of the processing of the input messages.
        """

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
        self.use_log = use_log
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
        self.am_paused = True
        self.am_crashed = False
        self.in_message_history = []
        self.out_message_history = []
        self.save_message_history = False

    def set_configs(self, local_config, cluster_config):
        self.cluster_config = cluster_config
        self.local_config = local_config
        self.hull = TestHull(self.cluster_config, self.local_config, self)
        self.operations = SimpleOps()
    
    async def simulate_crash(self):
        await self.hull.stop()
        self.am_crashed = True
        self.network.isolate_server(self)
        test_trace = self.network.test_trace
        await test_trace.note_crash(self)
        self.hull = None
        
    async def recover_from_crash(self, deliver=False, save_log=True, save_ops=True):
        if not save_log:
            self.log.close()
            if self.use_log == MemoryLog:
                self.log = MemoryLog()
            else:
                self.log = setup_sqlite_log(self.uri)
        if not save_ops:
            self.operations = SimpleOps()
        self.am_crashed = False
        self.hull = TestHull(self.cluster_config, self.local_config, self)
        await self.hull.start()
        self.network.reconnect_server(self, deliver=deliver)
        test_trace = self.network.test_trace
        await test_trace.note_recover(self)

    def get_state_code(self):
        if self.hull is None:
            return None
        return self.hull.get_state_code()
    
    def get_state(self):
        if self.hull is None:
            return None
        return self.hull.state

    async def get_term(self):
        if self.hull is None:
            return None
        return await self.hull.get_term()

    def get_leader_uri(self):
        if self.hull is None:
            return None
        if self.hull.get_state_code() == "LEADER":
            return self.uri
        return self.hull.state.leader_uri
        
    async def start_campaign(self):
        res =  await self.hull.start_campaign()
        test_trace = self.network.test_trace
        await test_trace.note_role_changed(self)
        return res
    
    async def send_heartbeats(self):
        return await self.hull.state.send_heartbeats()
    
    async def do_leader_lost(self):
        await self.hull.state.leader_lost()
        test_trace = self.network.test_trace
        await test_trace.note_role_changed(self)
        
    async def do_demote_and_handle(self, message=None):
        await self.hull.demote_and_handle(message)
        test_trace = self.network.test_trace
        await test_trace.note_role_changed(self)

    async def run_command(self, command, timeout=1.0):
        test_trace = self.network.test_trace
        await test_trace.note_command_started(self)
        res = await self.hull.run_command(command, timeout)
        await test_trace.note_command_finished(self)
        return res
        
    # Part of PilotAPI
    def get_log(self):
        return self.log

    # Part of PilotAPI
    async def process_command(self, command, serial):
        return await self.operations.process_command(command, serial)
        
    # Part of PilotAPI
    async def on_message(self, in_msg):
        if self.save_message_history:
            msg = self.hull.decode_message(in_msg)
            self.in_message_history.append(msg)
        await self.hull.on_message(in_msg)
        
    # Part of PilotAPI
    async def send_message(self, target, out_msg):
        msg = self.hull.decode_message(out_msg)
        self.logger.debug("queueing out msg %s", msg)
        self.out_messages.append(msg) 
        if self.save_message_history:
            self.out_message_history.append(msg)

    # Part of PilotAPI
    async def send_response(self, target, out_msg, in_reply):
        reply = self.hull.decode_message(in_reply)
        self.logger.debug("queueing out reply %s", reply)
        self.out_messages.append(reply) 
        if self.save_message_history:
            self.out_message_history.append(reply)
        
    async def start(self):
        await self.hull.start()
        
    async def start_election(self):
        await self.hull.campaign()

    async def disable_timers(self):
        return await self.hull.disable_timers()

    async def enable_timers(self, reset=True):
        return await self.hull.enable_timers(reset=reset)

    def replace_log(self, new_log=None):
        if self.use_log == SqliteLog:
            self.log.close()
        if new_log is None:
            if self.use_log == MemoryLog:
                self.log = MemoryLog()
            elif self.use_log == SqliteLog:
                self.log = setup_sqlite_log(self.uri)
        else:
            self.log = new_log
        self.hull.log = self.log
        self.hull.state.log = self.log
        return self.log
    
    def change_networks(self, network):
        if self.network and self.network != network:
            self.logger.info("%s changing networks, must be partition or heal, new net %s", self.uri, str(network))
        self.network = network

    def is_on_quorum_net(self):
        # this code could be simpler, but it gets called during
        # unsplit for test_trace purposes, so this has to be done
        min_nets = self.network.net_mgr.get_minority_networks()
        if min_nets is None:
            return True
        if self.network in min_nets:
            return False
        return True
        
    def block_network(self):
        self.blocked_in_messages = []
        self.blocked_out_messages = []
        self.in_messages = []
        self.out_messages = []
        self.block_messages = True
    
    def unblock_network(self, deliver=False):
        self.block_messages = False
        if not deliver:
            self.blocked_in_messages = None
            self.blocked_out_messages = None
            return
        for msg in self.blocked_in_messages:
            self.in_messages.append(msg)
            #print(f'\npending_in')
            #print(f'{msg}\n')
        for msg in self.blocked_out_messages:
            self.out_messages.append(msg)
            #print(f'\npending_out')
            #print(f'{msg}\n')
        self.blocked_in_messages = None
        self.blocked_out_messages = None
        
    def get_leader_id(self):
        if self.hull is None:
            return None
        if self.hull.state.state_code == "LEADER":
            return self.uri
        elif self.hull.state.state_code == "FOLLOWER":
            return self.hull.state.leader_uri
        else:
            return None

    async def do_next_in_msg(self):
        # sometimes test code wants to cycle individual servers specifically
        return await self.network.do_next_in_msg(self)
        
    async def do_next_out_msg(self):
        # sometimes test code wants to cycle individual servers specifically
        return await self.network.do_next_out_msg(self)

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
            
        self.am_paused = False
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
        self.am_paused = True

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


class SaveEvent(str, Enum):
    message_op = "MESSAGE_OP"
    role_changed = "ROLE_CHANGED"
    crashed = "CRASHED"
    recovered = "RECOVERED"
    started = "STARTED"
    net_partition = "NET_PARTITION"
    partition_healed = "PARTITION_HEALED"
    command_started = "COMMAND_STARTED"
    command_finished = "COMMAND_FINISHED"

    def __str__(self):
        return self.value
    
@dataclass
class NodeState:
    save_event: SaveEvent
    uri: str
    log_rec: LogRec
    commit_index: int
    term: int
    state_code: str
    on_quorum_net: bool = True
    is_paused: bool = False
    is_crashed: bool = False
    leader_id: Optional[str] = None
    voted_for: Optional[str] = None
    message_action: Optional[str] = None
    message: Optional[str] = None
    
    
@dataclass
class TableWrap:
    start_pos: int
    description: str
    test_path: Optional[str] = None
    test_doc_string: Optional[str] = None
    end_pos: Optional[int] = None
    lines: Optional[list] = None
    condensed: Optional[list] = None
    
class TestTrace:

    def __init__(self, cluster):
        self.cluster = cluster
        self.node_states = {}
        self.trace_lines = []
        self.table_wraps = {}
        self.current_wrap = None
        
    async def start(self):
        tl = []
        for uri,node in self.cluster.nodes.items():
            ns = self.node_states[uri] = await self.create_node_state(node)
            tl.append(deepcopy(ns))
            ns.save_event = None
        self.trace_lines.append(tl)
        
        
    async def create_node_state(self, node):
        ns = NodeState(save_event=SaveEvent.started,
                       uri=node.uri,
                       log_rec=await node.log.read(),
                       term=await node.log.get_term(),
                       commit_index=await node.log.get_commit_index(),
                       state_code=node.get_state_code(),
                       on_quorum_net=node.is_on_quorum_net(),
                       is_paused=node.am_paused,
                       is_crashed=node.am_crashed,
                       leader_id=node.get_leader_id(),
                       voted_for=await node.log.get_voted_for())
        return ns

    async def update_node_state(self, node, ns):
        ns.log_rec = await node.log.read()
        ns.term = await node.log.get_term()
        ns.on_quorum_net = node.is_on_quorum_net()
        ns.commit_index = await node.log.get_commit_index()
        ns.state_code = node.get_state_code()
        ns.is_paused = node.am_paused
        ns.is_crashed = node.am_crashed
        ns.leader_id = node.get_leader_id()
        ns.voted_for  = await node.log.get_voted_for()
        return ns


    def start_subtest(self, description, test_path_str=None, test_doc_string=None):
        old_st = self.current_wrap
        if old_st and old_st.end_pos is None:
            old_st.end_pos=len(self.trace_lines)-1,
        st = TableWrap(start_pos=len(self.trace_lines),
                          description=description,
                          test_path=test_path_str,
                          test_doc_string=test_doc_string)
        self.current_wrap = st
        self.table_wraps[st.start_pos] = st
        
    def end_subtest(self):
        st = self.current_wrap
        st.end_pos = len(self.trace_lines)
        self.current_wrap = None
        
    async def save_trace_line(self):
        # We write a new trace line for any change to any node, and each
        # trace line records everything about every node.
        # This is not efficient, but it cannot result in confusion about
        # order
        tl = []
        for uri,node in self.cluster.nodes.items():
            ns = self.node_states[uri]
            ns = await self.update_node_state(node, ns)
            tl.append(deepcopy(ns))
        self.trace_lines.append(tl)

    async def note_role_changed(self, node):
        ns = self.node_states[node.uri]
        ns.save_event = SaveEvent.role_changed
        await self.save_trace_line()
        ns.save_event = None

    async def note_command_started(self, node):
        ns = self.node_states[node.uri]
        ns.save_event = SaveEvent.command_started
        await self.save_trace_line()
        ns.save_event = None

    async def note_command_finished(self, node):
        ns = self.node_states[node.uri]
        ns.save_event = SaveEvent.command_finished
        await self.save_trace_line()
        ns.save_event = None

    async def note_partition(self, node):
        min_net = self.cluster.net_mgr.get_minority_networks()[0]
        ns = self.node_states[node.uri]
        ns.save_event = SaveEvent.net_partition
        await self.save_trace_line()
        ns.save_event = None

    async def note_heal(self, node):
        # just pick one
        ns = self.node_states[node.uri]
        ns.save_event = SaveEvent.partition_healed
        await self.save_trace_line()
        ns.save_event = None

    async def note_crash(self, node):
        ns = self.node_states[node.uri]
        ns.save_event = SaveEvent.crashed
        await self.save_trace_line()
        ns.save_event = None

    async def note_recover(self, node):
        ns = self.node_states[node.uri]
        ns.save_event = SaveEvent.recovered
        await self.save_trace_line()
        ns.save_event = None
    
    async def note_blocked_message(self, target, message):
        ns = self.node_states[target.uri]
        ns.save_event = SaveEvent.message_op
        ns.message = message
        ns.message_action = "blocked_in"
        await self.save_trace_line()
        ns.save_event = None
        ns.message = None
        ns.message_action = None

    async def note_queued_in_message(self, target, message):
        ns = self.node_states[target.uri]
        ns.save_event = SaveEvent.message_op
        ns.message = message
        ns.message_action = "queued_in"
        await self.save_trace_line()
        ns.save_event = None
        ns.message = None
        ns.message_action = None

    async def note_message_handled(self, target, message):
        ns = self.node_states[target.uri]
        ns.save_event = SaveEvent.message_op
        ns.message = message
        ns.message_action = "handled_in"
        await self.save_trace_line()
        ns.save_event = None
        ns.message = None
        ns.message_action = None

    async def note_blocked_send(self, sender, message):
        ns = self.node_states[sender.uri]
        ns.save_event = SaveEvent.message_op
        ns.message = message
        ns.message_action = "blocked_send"
        await self.save_trace_line()
        ns.save_event = None
        ns.message = None
        ns.message_action = None

    async def note_lost_send(self, sender, message):
        ns = self.node_states[sender.uri]
        ns.save_event = SaveEvent.message_op
        ns.message = message
        ns.message_action = "lost_send"
        await self.save_trace_line()
        ns.save_event = None
        ns.message = None
        ns.message_action = None

    async def note_message_sent(self, sender, message):
        ns = self.node_states[sender.uri]
        ns.save_event = SaveEvent.message_op
        ns.message = message
        ns.message_action = "sent"
        await self.save_trace_line()
        ns.save_event = None
        ns.message = None
        ns.message_action = None

    def to_condensed_org(self, include_legend=True):
        if len(self.trace_lines) == 0:
            return []
        tables = self.to_condensed_tables()
        all_rows = []
        for t_index, table in enumerate(tables):
            if table.test_path:
                try:
                    full_name, tfile, test_name = get_current_test()
                except Exception:
                    test_name = ""
                all_rows.append(f"* Test {test_name} from file {table.test_path}")
                all_rows.append("")
            if table.test_doc_string:
                all_rows.append(table.test_doc_string)
                all_rows.append("")
            if len(all_rows) > 1:
                break
        if include_legend:
            all_rows.append("")
            all_rows.append(" *[[condensed Trace Table Legend][Table legend]] located after last table in file*")
            all_rows.append("")
        for t_index, table in enumerate(tables):
            max_chars = 0
            # get the column widths
            row0 = table.condensed[0]
            col_widths = [0 for col in row0 ]
            trows = []
            for row in table.condensed:
                for col_index, col in enumerate(row):
                    col_widths[col_index] = max(col_widths[col_index], len(str(col)))
            trows.append(f"** {table.description}")
            for row in table.condensed:
                str_line = "| "
                for col_index, col in enumerate(row):
                    str_line += f"{col:{col_widths[col_index]}s} |"
                trows.append(str_line)
                max_chars = max(max_chars, len(str_line))
            #trows.append(f" End of {table.description}")
            trows.append('-' * max_chars)
            final_rows = [trows[0],]
            final_rows.append('-' * max_chars)
            final_rows.extend(trows[1:])
            all_rows.extend(final_rows)
            if False:
                for trow in final_rows:
                    print(trow)
        if include_legend:
            legend_path = Path(Path(__file__).parent, "table_legend.org")
            with open(legend_path, 'r') as f:
                buff = f.read()
            for lline in buff.split('\n'):
                all_rows.append(lline)
        return all_rows
    
    def to_csv(self):
        cols = []
        cols.append('event')
        cols.append('event_node')
        cols.append('message_sender')
        cols.append('message_target')
        cols.append('message_status')
        cols.append('message_type')
        cols.append('entries_count')
        cols.append('commit_index')
        cols.append('reply_entries_ok')
        cols.append('reply_max_index')
        for i in range(1, len(self.cluster.nodes) + 1):
            cols.append(f'n{i}-uri')
            cols.append(f'n{i}-state')
            cols.append(f'n{i}-term')
            cols.append(f'n{i}-on_quorum_net')
            cols.append(f'n{i}-last_index')
            cols.append(f'n{i}-last_term')
            cols.append(f'n{i}-commit_index')
            cols.append(f'n{i}-leader_uri')
            cols.append(f'n{i}-voted_for')
            cols.append(f'n{i}-is_crashed')
        csv_lines = [cols,]
        for line in self.trace_lines:
            cols = []
            for ns in line:
                if ns.save_event is not None:
                    cols.append(f'{ns.save_event}')
                    cols.append(str(ns.uri))
                    if ns.message_action:
                        cols.append(ns.message.sender)
                        cols.append(ns.message.receiver)
                        cols.append(str(ns.message_action))
                        cols.append(ns.message.code)
                        if ns.message.code == "append_entries":
                            cols.append(f'{len(ns.message.entries)}')
                            cols.append(f'{ns.message.commitIndex}')
                            cols.append('')
                            cols.append('')
                        elif ns.message.code == "append_response":
                            cols.append('')
                            cols.append('')
                            cols.append(f'{ns.message.success}')
                            cols.append(f'{ns.message.maxIndex}')
                        else:
                            cols.append('')
                            cols.append('')
                            cols.append('')
                            cols.append('')
                    else:
                        cols.append('')
                        cols.append('')
                        cols.append('')
                        cols.append('')
                        cols.append('')
                        cols.append('')
                        cols.append('')
                        cols.append('')
                    break
            in_order = []
            while len(in_order) < len(self.cluster.nodes):
                for ns in line:
                    for index, uri in enumerate(self.cluster.nodes):
                        if uri == ns.uri:
                            if index == len(in_order):
                                in_order.append(ns)
                                break
            for ns in in_order:
                cols.append(ns.uri)
                cols.append(str(ns.state_code))
                cols.append(str(ns.term))
                cols.append(str(ns.on_quorum_net))
                if ns.log_rec is None:
                    cols.append('0')
                    cols.append('0')
                else:
                    cols.append(str(ns.log_rec.index))
                    cols.append(str(ns.log_rec.term))
                cols.append(str(ns.commit_index))
                cols.append(f'{ns.leader_id}')
                cols.append(f'{ns.voted_for}')
                cols.append(f'{ns.is_crashed}')
            csv_lines.append(cols)
        return csv_lines

    def wrap_table(self, start_pos):
        if start_pos not in self.table_wraps:
            # we don't have instructions from the test code, so we just
            # make it up
            try:
                full_name, tfile, test_name = get_current_test()
            except Exception:
                test_name = "not in test, name unknown"
            wrap =  TableWrap(start_pos=start_pos,
                               description=test_name)
        else:
            wrap = self.table_wraps[start_pos]

        wrap.lines = []
        wrap.lines.append(wrap)
        pos = start_pos + 1
        while pos < len(self.trace_lines):
            wrap.lines.append(self.trace_lines[pos])
            if pos == wrap.end_pos:
                return wrap
            if pos in self.table_wraps:
                # this pos is the start of another table
                # nobody called end for this table
                wrap.end_pos = pos - 1
                return wrap
            pos += 1 
        wrap.end_pos = pos - 1
        return wrap
        
    def to_condensed_tables(self, include_index=False):
        tables = []
        table = self.wrap_table(0)
        tables.append(table)
        while table.end_pos + 1 < len(self.trace_lines):
            table = self.wrap_table(table.end_pos + 1)
            tables.append(table)

        def short_event(ns):
            choices = dict(ROLE_CHANGED="NEW ROLE",
                           MESSAGE_OP="MSG",
                           CRASHED="CRASH",
                           RECOVERED="RESTART",
                           NET_PARTITION="NETSPLIT",
                           PARTITION_HEALED="NETJOIN",
                           COMMAND_STARTED="CMD START",
                           COMMAND_FINISHED="CMD DONE",)
            if ns.save_event in choices:
                return choices[ns.save_event]
            return ns.save_event

        def message_to_trace(ns, message):
            if message.code == "append_entries":
                short_code = "entries"
            elif message.code == "append_response":
                short_code = "ent_reply"
            elif message.code == "request_vote":
                short_code = "give_vote"
            elif message.code == "request_vote_response":
                short_code = "vote"
            target = message.receiver.split("/")[-1]
            sender = message.sender.split("/")[-1]
            if message.sender == ns.uri:
                value = f' {short_code}->N-{target}'
            else:
                value = f' N-{sender}->{short_code}->'
            if message.code == "append_entries":
                value += f" li={message.prevLogIndex} lt={message.prevLogTerm}"
                value += f" ec={len(message.entries)} ci={message.commitIndex}"
            elif message.code == "request_vote":
                value += f" term={message.term} li={message.prevLogIndex} lt={message.prevLogTerm}"
            elif message.code == "append_response":
                value += f" ok={message.success} mi={message.maxIndex}"
            elif message.code == "request_vote_response":
                value += f" yes={message.vote} "
            else:
                raise Exception('no code for message type')
            return value

        for table in tables:
            table.condensed = rows = []
            cols = []
            if include_index:
                cols.append("idx")
            cols.append('event') # node id, event_type
            start_line = self.trace_lines[table.start_pos]
            for index,ns in enumerate(start_line):
                cols.append(f' N-{index+1}')
                cols.append(f' N-{index+1}')  # # message type + sender/target, or action
                cols.append(f' N-{index+1}' )
            rows.append(cols)
            cols = []
            if include_index:
                cols.append("")
            cols.append("node ")
            for index,ns in enumerate(start_line):
                cols.append(f' Role')
                cols.append(f' Op')
                cols.append(f' Delta')
            rows.append(cols)
            events_to_show = []
            for pos, line in enumerate(self.trace_lines[table.start_pos: table.end_pos + 1]):
                if pos == table.start_pos or pos == table.end_pos:
                    events_to_show.append((pos,line))
                    continue
                for index, ns in enumerate(line):
                    if ns.save_event is not None:
                        if ns.save_event == SaveEvent.message_op:
                            # we are only going to show the trace if the
                            # resender or receiver is a leader, and only if the
                            # condition is sent or handled
                            if ns.state_code == "LEADER" or ns.state_code  == "CANDIDATE":
                                if ns.message_action in ("sent", "handled_in"):
                                    events_to_show.append((pos,line))
                        else:
                            events_to_show.append((pos, line))
            last_states = {}
            for subpos,line_spec in enumerate(events_to_show):
                pos,line = line_spec
                cols = []
                col_done = False
                if include_index:
                    cols.append(f" {pos} ")
                # do the op event column
                for index, ns in enumerate(line):
                    if ns.save_event is not None and not col_done:
                        cols.append(f" N-{index+1} ")
                        col_done = True
                # fix up any empty log records, it makes it clearer that something changed
                for index, ns in enumerate(line):
                    # do the role column
                    if ns.state_code == "FOLLOWER" or ns.state_code is None:
                        cols.append(' FLWR ')
                    elif ns.state_code == "CANDIDATE":
                        cols.append(' CNDI ')
                    elif ns.state_code == "LEADER":
                        cols.append(' LEAD ')
                    # do the op column
                    if ns.save_event is None:
                        cols.append('')
                    else:
                        if ns.save_event == SaveEvent.message_op:
                            if ns.state_code != "FOLLOWER" and ns.message_action in ("sent", "handled_in"):
                                cols.append(message_to_trace(ns, ns.message))
                        else:
                            cols.append(f" {short_event(ns)} ")
                    # do the delta column
                    # see if state changed
                    if ns.log_rec is None:
                        # fake it up for comparisons
                        ns.log_rec = LogRec()

                    d_t = ""
                    d_lt = ""
                    d_li = ""
                    d_ci = ""
                    d_net = ""
                    if str(ns.save_event) == "PARTITION_HEALED" and subpos == 0:
                        # can happen if netjoin is first in table
                        # due to subtest calls
                        d_net = " n=1"
                    if subpos > 0:
                        
                        last = last_states[index]
                        if ns.term != last.term:
                            d_t = f" t={ns.term}"
                        if ns.log_rec.term != last.log_rec.term:
                            d_lt = f" lt={ns.log_rec.term}"
                        if ns.log_rec.index != last.log_rec.index:
                            d_li = f" li={ns.log_rec.index}"
                        if ns.commit_index != last.commit_index:
                            d_ci = f" ci={ns.commit_index}"
                        if ns.on_quorum_net:
                            if not last.on_quorum_net:
                                d_net = " n=1"
                            else:
                                d_net = ""
                        else:
                                
                            d_net = " n=2"
                    cols.append(d_t + d_lt + d_li + d_ci + d_net)
                    last_states[index] = ns
                rows.append(cols)
        return tables
        
        
class PausingCluster:

    def __init__(self, node_count, use_log=MemoryLog):
        self.node_uris = []
        self.nodes = dict()
        self.logger = logging.getLogger("PausingCluster")
        self.auto_comms_flag = False
        self.async_handle = None
        self.test_trace = TestTrace(self)
        for i in range(node_count):
            nid = i + 1
            uri = f"mcpy://{nid}"
            self.node_uris.append(uri)
            t1s = PausingServer(uri, self, use_log=use_log)
            self.nodes[uri] = t1s
        self.net_mgr = NetManager(self.nodes, self.nodes)
        self.net_mgr.set_test_trace(self.test_trace)
        net = self.net_mgr.setup_network()
        for uri, node in self.nodes.items():
            node.network = net
        assert len(self.node_uris) == node_count

    def build_cluster_config(self, heartbeat_period=1000,
                             election_timeout_min=10000,
                             election_timeout_max=20000):
        
            cc = ClusterConfig(node_uris=self.node_uris,
                               heartbeat_period=heartbeat_period,
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

    async def start(self, only_these=None, timers_disabled=True):
        await self.test_trace.start()
        for uri, node in self.nodes.items():
            await node.start()
            if timers_disabled:
                await node.disable_timers()

    async def split_network(self, segments):
        await self.net_mgr.split_network(segments)
        
    async def unsplit(self):
        await self.net_mgr.unsplit()

    async def disable_timers(self):
        for node in self.nodes.values():
            await node.disable_timers()
            
    async def enable_timers(self, reset=True):
        for node in self.nodes.values():
            await node.enable_timers(reset=reset)
            
    def get_leader(self):
        for uri, node in self.nodes.items():
            if node.hull.state.state_code == "LEADER":
                return node
        return None
    
    async def run_sequence(self, sequence):
        await sequence.do_setup()
        # may raise timeout
        result = await sequence.wait_till_done()
        await sequence.do_teardown()
        return result

    async def run_election(self, timeout=1.0):
        voters = []
        net = self.net_mgr.get_majority_network()
        for uri, node in net.nodes.items():
            if node.block_messages:
                continue
            voters.append(uri)
        sequence = SPartialElection(self, voters=voters, timeout=timeout)
        res = await self.run_sequence(sequence)
        return res
        
    async def run_command(self, command, timeout=1.0):
        voters = []
        net = self.net_mgr.get_majority_network()
        for uri, node in net.nodes.items():
            if node.block_messages:
                continue
            voters.append(uri)
        sequence = SPartialCommand(self, command, voters=voters, timeout=timeout)
        res = await self.run_sequence(sequence)
        return res
        
    async def post_in_message(self, message):
        # special situation, called when trigger trapped on out message,
        # but wants it to be delivered before pause
        await self.net_mgr.post_in_message(message)

    async def deliver_all_pending(self,  quorum_only=False, out_only=False):
        """ Cluster "mamual" message delivery control, meaning this methond delivers
        messages from node to now one at a time untill no more messages are pending. 
        Delivery includes triggering the code under test to process the messages,
        and collecting the replies. It is intended to be used when the test code
        has set up conditions that will result in a number of message interchanges
        but they are a finite and deterministic sequence. This mechanism is not
        suitabe for use when the timers for election_timeout et. al. are running.
        A typical use of this is to setup the conditions for an election to happen
        and then to let all the messages fly, then check that the election completed.
        If the caller specifies quorum_only == True, and the netork has been split
        into segments, then only the containing a majority of the servers will
        participate in the message delivery. See NetManager.deliver_all_pending
        for more details.
        If the caller specifies out_only == True, then the process 
        will only move messages from out to in buffers, not trigger the
        input processing. This can be useful if a test wants to have
        granular control of the processing of the input messages. 
        See Network.deliver_all_pending for more details.
        """
        return await self.net_mgr.deliver_all_pending(quorum_only=quorum_only, out_only=out_only)

    async def auto_comms_runner(self, quorum_only=False):
        try:
            self.logger.info("-----------------------------auto_comms_runner starting")
            while self.auto_comms_flag:
                res = await self.deliver_all_pending(quorum_only)
                count = 0
                if res['multiple_networks']:
                    for subres in res['result_list']:
                        count += subres['count']
                else:
                    count = res['count']
                if count == 0:
                    await asyncio.sleep(0.00001)
            self.async_handle = None
            self.logger.info("-----------------------------auto_comms_runner exiting")
        except Exception as exc:
            self.logger.info("error trying to deliver messages %s", traceback.format_exc())

    async def start_auto_comms(self, quorum_only=False):
        """ This method creates a task that runs the normal deliver_all_pending method
        continuously until told to stop. This is useful for simplifying test code that
        deals with long sequences of more or less normal operations, so you don't have
        to clutter up the code with constant calls to deliver_all_pending.
        The quorum_only flag is passed to the deliver_all_pending on each call.
        """
        if self.auto_comms_flag:
            return
        try:
            self.auto_comms_flag = True
             # don't know why, but things can get delivered out of order without this
            await self.deliver_all_pending()
            loop = asyncio.get_event_loop()
            self.async_handle = loop.call_soon(lambda:
                                               loop.create_task(self.auto_comms_runner(quorum_only)))
            self.logger.debug("scheduled auto_comms_runner")
        except Exception as exc:
            self.logger.error("error trying to setup auto_comms runner %s", traceback.format_exc())
        
    async def stop_auto_comms(self):
        if self.auto_comms_flag:
            if self.async_handle:
                self.async_handle.cancel()
                await asyncio.sleep(0)
                self.async_handle = None
                self.logger.debug("canceled auto_comms_runner")
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
        
class CommandFailedTaskGroup(Exception):
    """Exception raised to terminate a task group due to command returning retry, redirect, timeout, etc.."""
    
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
                orig_index = await node.log.get_commit_index()
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
        self.command_result = await node.run_command(command, timeout=0.1)
        
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

class SPartialElection(StdSequence):

    def __init__(self, cluster, voters, timeout=1):
        super().__init__(cluster=cluster, name="PartialElection")
        self.timeout = timeout
        self.voters = voters
        self.logger = logging.getLogger('PausingServer')
        self.done_count = 0
        self.expected_count = 0

    async def do_setup(self):
        for uri in self.voters:
            node = self.cluster.nodes[uri]
            node.clear_triggers()
            node.set_trigger(WhenElectionDone(self.voters))
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
                for uri in self.voters:
                    node = self.cluster.nodes[uri]
                    tg.create_task(self.runner_wrapper(node))
                    self.logger.debug('scheduled runner task for node %s in %s', node.uri, self.name)
                tg.create_task(do_timeout(self.timeout))
        except* TimeoutTaskGroup:
            raise TestServerTimeout('timeout on wait till done on %s!', self.name)
        
    async def do_teardown(self):
        for uri in self.voters:
            node = self.cluster.nodes[uri]
            node.clear_triggers()
            
class SPartialCommand(StdSequence):

    def __init__(self, cluster, command, voters, timeout=1):
        super().__init__(cluster=cluster, name="PartialCommand")
        self.timeout = timeout
        self.command = command
        self.voters = voters
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
        for uri in self.voters:
            if uri not in self.network.nodes:
                raise Exception(f'bad setup, {voter} not in majority network')
            node = self.network.nodes[uri]
            node.clear_triggers()
            if node.hull.state.state_code == "LEADER":
                self.leader = node
                orig_index = await node.log.get_commit_index()
                self.target_index = orig_index + 1
                break
        for uri in self.voters:
            node = self.network.nodes[uri]
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
                if node.uri not in self.voters:
                    continue
                await node.run_till_triggers()
        self.done_count += 1
        
    async def command_wrapper(self, node, command, timeout=0.1):
        self.logger.debug("Running command %s at  %s", command, node.uri)
        self.command_result = await node.run_command(command, timeout=timeout)
        self.logger.debug("%s command_result = %s", node.uri, self.command_result.__dict__)
        if self.command_result.result is None:
            raise CommandFailedTaskGroup(f'command_result = {self.command_result.__dict__}')

    async def wait_till_done(self):
        async def do_timeout(timeout):
            start_time = time.time()
            while self.done_count < self.expected_count and self.command_result is None:
                await asyncio.sleep(timeout/100.0)
            if not self.command_result and time.time() - start_time >= timeout:
                raise TimeoutTaskGroup()
        try:
            self.command_result = None
            async with asyncio.TaskGroup() as tg:
                tg.create_task(self.command_wrapper(self.leader, self.command, timeout=self.timeout))
                for uri in self.voters:
                    node = self.network.nodes[uri]
                    tg.create_task(self.runner_wrapper(node))
                    self.logger.debug('scheduled runner task for node %s in %s', node.uri, self.name)
                tg.create_task(do_timeout(self.timeout))
        except* TimeoutTaskGroup:
            raise TestServerTimeout('timeout on wait till done on %s!', self.name)
        except* CommandFailedTaskGroup:
            self.logger.debug('command failed, returning details')
        return self.command_result
    
    async def do_teardown(self):
        for uri in self.voters:
            node = self.network.nodes[uri]
            node.clear_triggers()
            
        if self.restore_auto:
            await self.cluster.start_auto_comms()
