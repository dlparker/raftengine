import asyncio
import os
import json
import logging
import time
import shutil
from copy import deepcopy
from pathlib import Path

from raftengine.api.deck_config import ClusterInitConfig
from raftengine.api.log_api import LogRec
from raftengine.api.pilot_api import PilotAPI
from raftengine.api.types import ClusterSettings
from raftengine.api.snapshot_api import SnapShot, SnapShotToolAPI
from raftengine.deck.deck import Deck
from dev_tools.triggers import TriggerSet
from dev_tools.operations import SimpleOps
from raftengine.extras.memory_log import MemoryLog
from raftengine.extras.sqlite_log import SqliteLog
from raftengine.extras.lmdb_log import LmdbLog
from raftengine.extras.hybrid_log import HybridLog

class PausingServer(PilotAPI):

    def __init__(self, uri, cluster, use_log):
        self.uri = uri
        self.cluster = cluster
        if use_log is None:
            log_type = os.environ.get('RAFT_LOG_DEFAULT', "memory")
            if log_type == "memory":
                use_log = MemoryLog
            elif log_type == "sqlite":
                use_log = SqliteLog
            elif log_type == "lmdb":
                use_log = LmdbLog
            elif log_type == "hybrid":
                use_log = HybridLog
        self.use_log = use_log
        self.cluster_init_config = None
        self.local_config = None
        self.deck = None
        self.in_messages = []
        self.out_messages = []
        self.lost_out_messages = []
        self.logger = logging.getLogger("PausingServer")
        self.log = setup_log(self, use_log)
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
        self.interceptors = {}
        self.deck_stopped = False

    def __str__(self):
        return self.uri

    def set_configs(self, local_config, cluster_config, use_ops=SimpleOps):
        self.cluster_init_config = cluster_config
        self.local_config = local_config
        self.deck = Testdeck(self.cluster_init_config, self.local_config, self)
        self.ops_class = use_ops
        self.operations = use_ops(self)

    async def change_cluster_config(self, cluster_config):
        # in case test reuses one improperly, which is convenient
        self.cluster_init_config = deepcopy(cluster_config)
        return await self.deck.change_cluster_config(self.cluster_init_config)

    async def get_cluster_config(self):
        # in case test reuses one improperly, which is convenient
        return await self.deck.get_cluster_config()

    async def simulate_crash(self):
        await self.deck.stop()
        # do not stop the log, for memory log that will clear the data
        # await self.log.stop()
        self.am_crashed = True
        self.network.isolate_server(self)
        self.in_messages = []
        self.out_messages = []
        test_trace = self.network.test_trace
        await test_trace.note_crash(self)
        self.deck = None

    async def recover_from_crash(self, deliver=False, save_log=True, save_ops=True):
        if not save_log:
            await self.log.stop()
            self.log = setup_log(self, self.use_log)
            await self.log.start()
        if not save_ops:
            self.operations = self.ops_class(self)
        self.am_crashed = False
        self.deck = Testdeck(self.cluster_init_config, self.local_config, self)
        await self.deck.start()
        self.network.reconnect_server(self, deliver=deliver)
        test_trace = self.network.test_trace
        await test_trace.note_recover(self)

    def get_role_name(self):
        if self.deck is None:
            return None
        return self.deck.get_role_name()

    def get_message_problem_history(self, clear=False):
        if self.deck is None:
            return None
        return self.deck.get_message_problem_history(clear)

    def get_role(self):
        if self.deck is None:
            return None
        return self.deck.get_role()

    async def get_term(self):
        if self.deck is None:
            return None
        return await self.deck.get_term()

    def get_leader_uri(self):
        if self.deck is None:
            return None
        if self.deck.get_role_name() == "LEADER":
            return self.uri
        return self.deck.leader_uri

    async def start_campaign(self, authorized=False):
        res = await self.deck.start_campaign(authorized=authorized)
        test_trace = self.network.test_trace
        await test_trace.note_role_changed(self)
        return res

    async def transfer_power(self, other_uri):
        res =  await self.deck.transfer_power(other_uri)
        return res

    async def send_heartbeats(self, target_only=None):
        return await self.deck.role.send_heartbeats(target_only)

    async def do_leader_lost(self):
        await self.deck.role.leader_lost()
        test_trace = self.network.test_trace
        await test_trace.note_role_changed(self)

    async def do_demote_and_handle(self, message=None):
        await self.deck.demote_and_handle(message)
        test_trace = self.network.test_trace
        await test_trace.note_role_changed(self)

    async def run_command(self, command, timeout=1.0):
        test_trace = self.network.test_trace
        await test_trace.note_command_started(self)
        res = await self.deck.run_command(command, timeout)
        await test_trace.note_command_finished(self)
        return res

    # Part of PilotAPI
    def get_log(self):
        return self.log

    # Part of PilotAPI
    async def process_command(self, command, serial):
        return await self.operations.process_command(command, serial)

    async def add_interceptor(self, interceptor, msg_op="out", msg_type="append_entries"):
        index = f"{msg_op}:{msg_type}"
        print(f"adding {index}")
        self.interceptors[index] = interceptor
        
    # Part of PilotAPI
    async def send_message(self, target, out_msg, serial_number):
        msg = self.deck.decode_message(out_msg)
        index = f"out:{msg.code}"
        if index in self.interceptors:
            self.logger.debug("Calling out interceptor for msg %s", msg)
            cont = await self.interceptors[index](target, msg, serial_number)
            if not cont:
                self.logger.debug("Interceptor bypassed msg %s", msg)
                return
        self.logger.debug("queueing out msg %s", msg)
        self.out_messages.append(msg)
        if self.save_message_history:
            self.out_message_history.append(msg)

    # Part of PilotAPI
    async def send_response(self, target, out_msg, in_reply, orig_serial_number):
        reply = self.deck.decode_message(in_reply)
        index = f"out:{reply.code}"
        if index in self.interceptors:
            self.logger.debug("Calling out interceptor for msg %s", reply)
            cont = await self.interceptors[index](target, reply, reply.serial_number)
            if not cont:
                self.logger.debug("Interceptor bypassed msg %s", reply)
                return
        self.logger.debug("queueing out reply %s", reply)
        self.out_messages.append(reply)
        if self.save_message_history:
            self.out_message_history.append(reply)

    # Part of PilotAPI
    async def create_snapshot(self, index:int , term: int) -> SnapShot:
        return await self.operations.create_snapshot(index, term)
    
    # Part of PilotAPI
    async def begin_snapshot_import(self, snapshot:SnapShot) -> SnapShotToolAPI:
        return await self.operations.begin_snapshot_import(snapshot)

    # Part of PilotAPI
    async def begin_snapshot_export(self, snapshot:SnapShot) -> SnapShotToolAPI:
        return await self.operations.begin_snapshot_export(snapshot)

    # Part of PilotAPI
    async def stop_commanded(self) -> None:
        self.logger.debug('%s stop_commanded from deck', self.uri)
        self.deck_stopped = True
        #await self.cluster.remove_node(self.uri)
        
    async def on_message(self, in_msg):
        msg = self.deck.decode_message(in_msg)
        if self.save_message_history:
            self.in_message_history.append(msg)
        index = f"in:{msg.code}"
        if index in self.interceptors:
            self.logger.debug("Calling in msg interceptor for msg %s", msg)
            cont = await self.interceptors[index](msg.sender, msg, msg.serial_number)
            if not cont:
                self.logger.debug("Interceptor bypassed msg %s", msg)
                return
        await self.deck.on_message(in_msg)
        
    async def exit_cluster(self, callback=None, timeout=10.0):
        await self.deck.exit_cluster(callback, timeout)

    async def start(self):
        await self.log.start()
        await self.deck.start()

    async def stop(self):
        await self.deck.stop()
        await self.log.stop()

    async def tmp_stop(self):
        # don't stop the log, expect to restart it
        await self.deck.stop()

    async def start_and_join(self, leader_uri, callback=None, timeout=10.0):
        await self.log.start()
        await self.deck.start_and_join(leader_uri, callback, timeout)

    async def start_election(self):
        await self.deck.campaign()

    async def disable_timers(self):
        return await self.deck.disable_timers()

    async def enable_timers(self, reset=True):
        return await self.deck.enable_timers(reset=reset)

    async def take_snapshot(self, timeout=2.0):
        return await self.deck.take_snapshot(timeout=timeout)
    
    async def fake_command(self, op, value):
        last_index = await self.log.get_last_index()
        rec = LogRec(index=last_index + 1, term=1, command=f"{op} {value}")
        await self.log.append(rec)
        await self.log.mark_committed(rec.index)
        if op == "add":
            self.operations.total += value
        elif op == "sub":
            self.operations.total -= value
        else:
            raise Exception(f'unexpected op "{op}"')
        await self.log.mark_applied(rec.index)

    async def fake_command2(self, command):
        last_index = await self.log.get_last_index()
        res,error = await self.operations.process_command(command, last_index + 1)
        rec = LogRec(index=last_index + 1, term=1, command=command)
        await self.log.mark_committed(rec.index)
        await self.log.append(rec)
        await self.log.mark_applied(rec.index)
        return rec

    async def replace_log(self, new_log=None):
        await self.log.stop()
        if new_log is None:
            self.log = setup_log(self, self.use_log)
            await self.log.start()
        else:
            self.log = new_log
        self.deck.log = self.log
        self.deck.role.log = self.log
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
        if self.deck is None:
            return None
        if self.deck.role.role_name == "LEADER":
            return self.uri
        elif self.deck.role.role_name == "FOLLOWER":
            return self.deck.role.leader_uri
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
        deck = self.deck
        if deck and deck.role:
            self.logger.debug('cleanup stopping %s %s', deck.role, self.uri)
            handle =  deck.role_async_handle
            await deck.role.stop()
            if handle:
                self.logger.debug('after %s %s stop, handle.cancelled() says %s',
                                 deck.role, self.uri, handle.cancelled())
            ohandle =  deck.join_waiter_handle
            if ohandle:
                self.logger.debug('after %s %s stop, join_waiter handle.cancelled() says %s',
                                 deck.role, self.uri, ohandle.cancelled())
        if deck:
            self.deck = None
            del deck
        await self.log.stop()
        self.logger.debug('cleanup done on %s', self.uri)

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
            if self.trigger and hasattr(self.trigger, 'dump_condition'):
                print(await self.trigger.dump_condition(self))
                res = await self.trigger.is_tripped(self)
                raise Exception(f'{self.uri} timeout waiting for triggers, condition tripped = {res}')
        self.logger.info("-----!!!! PAUSE !!!!----- %s run_till_triggers complete, pausing", self.uri)
        self.am_paused = True
        return # all triggers tripped as required by mode flags, so pause ops

    async def fetch_log(self, start_rec, end_rec):
        if start_rec == 0:
            start_rec = 1
        if end_rec == -1:
            end_rec = await self.log.get_last_index()
        data = []
        for i in range(start_rec, end_rec + 1):
            data.append(await self.log.read(i))
        return data

    async def dump_log(self, start_rec=1, end_rec=-1):
        data = await self.fetch_log(start_rec, end_rec)
        for rec in data:
            jdata = json.dumps(rec, default=lambda o: o.__dict__, indent=4)
            print(jdata)

    async def dump_stats(self):
        if self.deck.role.role_name == "FOLLOWER":
            leaderId=self.deck.role.leader_uri
        else:
            leaderId=None
        stats = dict(uri=self.uri,
                     role_name=self.deck.role.role_name,
                     term=await self.log.get_term(),
                     prevLogIndex=await self.log.get_last_index(),
                     prevLogTerm=await self.log.get_last_term(),
                     leaderId=leaderId)
        return stats



class Testdeck(Deck):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.break_on_message_code = None
        self.explode_on_message_code = None
        self.corrupt_message_with_code = None
        self.role_run_later_def = None
        self.timers_disabled = False
        self.wrapper_logger = logging.getLogger("SimulatedNetwork")
        self.await_message = True

    # For testing only
    async def change_cluster_config(self, init: ClusterInitConfig):
        # cant add or remove  nodes here, just update settings
        await self.log.start()
        config = await self.get_cluster_config()
        settings = ClusterSettings(heartbeat_period=init.heartbeat_period,
                                   election_timeout_min=init.election_timeout_min,
                                   election_timeout_max=init.election_timeout_max,
                                   max_entries_per_message=init.max_entries_per_message,
                                   use_pre_vote=init.use_pre_vote,
                                   use_check_quorum=init.use_check_quorum,
                                   use_dynamic_config=init.use_dynamic_config)
        config.settings = settings
        await self.log.save_cluster_config(config)
        res = self.current_config = await self.cluster_ops.get_cluster_config()
        return res

    async def on_message(self, message):
        dmsg = self.decode_message(message)
        if self.break_on_message_code == dmsg.get_code():
            print('here to catch break')
        if self.explode_on_message_code == dmsg.get_code():
            result = await super().on_message(b'{"code":"foo"}')
        if self.corrupt_message_with_code == dmsg.get_code():
            dmsg.entries = [dict(a=1),]
            self.wrapper_logger.error('%s corrupted message by inserting garbage as log rec', self.local_config.uri)
            result = await self.inner_on_message(dmsg)
        else:
            result = await super().on_message(message)
        return result

    async def role_run_after(self, delay, target):
        self.role_run_later_def = dict(role_name=self.role.role_name,
                                        delay=delay, target=target)
        if not self.timers_disabled:
            await super().role_run_after(delay, target)

    async def disable_timers(self):
        self.timers_disabled = True
        if self.role_async_handle:
            self.role_async_handle.cancel()
        self.role_async_handle = None

    async def enable_timers(self, reset=True):
        if reset:
            if self.role.role_name == "FOLLOWER":
                self.last_leader_contact = time.time()
            elif self.role.role_name == "LEADER":
                self.last_broadcast_time = time.time()
        if self.role_run_later_def:
            await super().role_run_after(self.role_run_later_def['delay'],
                                          self.role_run_later_def['target'])
        self.timers_disabled = False

class HL(HybridLog):
       
    async def start(self):
        await self.lmdb_log.start()
        await self.sqlite_log.start()
        #await self.sqlwriter.start(self.sqlwriter_callback, self.handle_writer_error, inprocess=True)
        self.sqlwriter = None
        

def setup_log(server, use_log_class, reset=True):
    number = server.uri.split('/')[-1]
    path_root = Path('/tmp', f"pserver_{number}")
    if use_log_class == MemoryLog:
        log = MemoryLog()
        return log
    elif use_log_class == SqliteLog:
        path = Path(str(path_root) +'.db')
        if path.exists() and reset:
            path.unlink()
        log = SqliteLog(path)
    elif use_log_class == LmdbLog:
        path = Path(str(path_root) +'.lmdb')
        if path.exists():
            if reset:
                shutil.rmtree(path)
                path.mkdir()
        else:
            path.mkdir()
        log = LmdbLog(path)
    elif use_log_class == HybridLog:
        path = Path(str(path_root) +'.hybrid')
        if path.exists():
            if reset:
                shutil.rmtree(path)
                path.mkdir()
        else:
            path.mkdir()
        #log = HybridLog(path)
        log = HL(path)
    else:
        raise Exception(f"don't know log type {use_log_class}")
    return log
