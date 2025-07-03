import json
import logging
import time


class NetManager:

    def __init__(self, start_nodes:dict):
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

    def add_node(self, node):
        if self.quorum_segment:
            self.quorum_segment.add_node(node)
        else:
            self.full_cluster.add_node(node)

    def remove_node(self, uri):
        if self.quorum_segment:
             if uri in self.quorum_segment.nodes:
                 node = self.quorum_segment.nodes[uri]
                 self.quorum_segment.remove_node(node)
                 return
             for seg in self.other_segments:
                if uri in seg.nodes:
                    node = seg.nodes[uri]
                    seg.remove_node(node)
                    return
        if uri in self.full_cluster.nodes:
            node = self.full_cluster.nodes[uri]
            self.full_cluster.remove_node(node)

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
        """ This does the final part of the work for the Cluster "manual"
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
            # since a node can exit during the loop, we need to make a copy of the node list
            # and iterate on that
            nodes = list(self.nodes.values())
            for node in nodes:
                node.am_paused = False
                if len(node.in_messages) > 0 and not out_only:
                    try:
                        msg = await node.do_next_in_msg()
                    except:
                        if node.deck is None:
                            # node can get stop_commanded during this loop
                            continue
                        else:
                            raise
                    if msg:
                        count += 1
                        in_ledger.append(msg)
                        any = True
                if len(node.out_messages) > 0:
                    try:
                        msg = await node.do_next_out_msg()
                    except:
                        if node.deck is None:
                            # node can get stop_commanded during this loop
                            continue
                        else:
                            raise
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
        stime = time.perf_counter()
        start_state = node.deck.role.role_name
        stime = time.perf_counter()
        await node.on_message(json.dumps(msg, default=lambda o:o.__dict__))
        etime = time.perf_counter() - stime
        await self.test_trace.note_message_handled(node, msg, etime)
        if start_state != node.deck.role.role_name:
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
            self.logger.info("%s target is not on this network, losing message %s", node.uri, msg)
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
