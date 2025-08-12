import asyncio
import dataclasses
import logging
import traceback
from pathlib import Path

import pytest

from dev_tools.sequences import SPartialElection, SPartialCommand
from dev_tools.network_sim import NetManager
from dev_tools.pausing_server import PausingServer, SimpleOps
from dev_tools.test_trace import TestTrace
from raftengine.api.deck_config import ClusterInitConfig, LocalConfig

class PausingCluster:

    def __init__(self, node_count, use_log=None):
        self.use_log = use_log
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
            t1s = PausingServer(uri, self, use_log=self.use_log)
            self.nodes[uri] = t1s
        self.net_mgr = NetManager(self.nodes)
        self.net_mgr.set_test_trace(self.test_trace)
        net = self.net_mgr.setup_network()
        for uri, node in self.nodes.items():
            node.network = net
        assert len(self.node_uris) == node_count
        self.cluster_init_config = None

    def build_cluster_config(self, heartbeat_period=1000,
                             election_timeout_min=10000,
                             election_timeout_max=20000,
                             use_pre_vote=True,
                             use_check_quorum=True,
                             use_dynamic_config=False):

        c_list = self.node_uris[::]
        cc = ClusterInitConfig(node_uris=c_list,
                               heartbeat_period=heartbeat_period,
                               election_timeout_min=election_timeout_min,
                               election_timeout_max=election_timeout_max,
                               max_entries_per_message=10,
                               use_pre_vote=use_pre_vote,
                               use_dynamic_config=use_dynamic_config)

        return cc

    def set_configs(self, cluster_config=None, use_ops=SimpleOps):
        if cluster_config is None:
            cluster_config = self.build_cluster_config()
        self.cluster_init_config = cluster_config
        self.use_ops = use_ops
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
            node.set_configs(local_config, cc, use_ops=use_ops)

    async def add_node(self):
        nid = len(self.nodes) + 1 # one offset
        uri = f"mcpy://{nid}"
        self.node_uris.append(uri)
        ps = PausingServer(uri, self, use_log=self.use_log)
        self.nodes[uri] = ps
        node_uris=self.node_uris,
        self.net_mgr.add_node(ps)
        local_config = LocalConfig(uri=uri,
                                   working_dir='/tmp/',
                                   )
        ps.set_configs(local_config, self.cluster_init_config, use_ops=self.use_ops)
        await self.test_trace.add_node(ps)
        return ps

    async def remove_node(self, node_uri):
        self.net_mgr.remove_node(node_uri)
        node = self.nodes[node_uri]
        await node.cleanup()
        del self.nodes[node_uri]

    async def start(self, only_these=None, timers_disabled=True):
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
            if node.deck.role.role_name == "LEADER":
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

    async def run_command(self, command, timeout=1.0, voters=None):
        if voters is None:
            net = self.net_mgr.get_majority_network()
            voters = []
            for uri, node in net.nodes.items():
                if node.block_messages or node.am_crashed:
                    self.logger.debug("cluster run_command skipping node %s", node.uri)
                    continue
                voters.append(uri)
        self.logger.debug("cluster running command at nodes %s", voters)
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

    async def save_traces(self):
        await self.test_trace.test_done()
        self.test_trace.save_json()
        self.test_trace.save_features()


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
        await the_cluster.save_traces()
        await the_cluster.cleanup()
        tasks = asyncio.all_tasks(asyncio.get_event_loop())
        tasks = [t for t in tasks if not t.done()]
        for task in tasks:
            task.cancel()

        # Wait for all tasks to complete, ignoring any CancelledErrors                                  
        try:
            await asyncio.wait(tasks)
        except asyncio.exceptions.CancelledError:
            pass
        



