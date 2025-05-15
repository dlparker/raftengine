import asyncio
import logging
import time

from dev_tools.triggers import WhenElectionDone, WhenHasAppliedIndex, \
    WhenCommitIndexSent


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
            if node.hull.role.role_name == "LEADER":
                self.leader = node
                orig_index = await node.log.get_commit_index()
                self.target_index = orig_index + 1
                break
        for uri,node in self.network.nodes.items():
            trigger = WhenHasAppliedIndex(self.target_index)
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
            await node.hull.role.send_heartbeats()
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
            if node.hull.role.role_name == "LEADER":
                self.leader = node
                orig_index = await node.log.get_commit_index()
                self.target_index = orig_index + 1
                break
        if self.target_index is None:
            raise Exception('cannot start command, no leader found')
        for uri in self.voters:
            node = self.network.nodes[uri]
            trigger = WhenHasAppliedIndex(self.target_index)
            self.logger.debug("set %s trigger for node %s", trigger, node)
            node.set_trigger(trigger)
            self.expected_count += 1
        self.logger.debug("Setup partial command sequence, will run command at %s for nodes %s", node.uri, self.voters)

    async def runner_wrapper(self, node):
        # wait until has commit index
        await node.run_till_triggers()
        if node == self.leader:
            # also need to send heartbeats so others get the commit index update
            self.logger.debug("Leader %s commit to %d, triggering heartbeats", node.uri, self.target_index)
            node.clear_triggers()
            await node.hull.role.send_heartbeats()
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


class TimeoutTaskGroup(Exception):
    """Exception raised to terminate a task group due to timeout."""


class CommandFailedTaskGroup(Exception):
    """Exception raised to terminate a task group due to command returning retry, redirect, timeout, etc.."""


class TestServerTimeout(Exception):
    """Exception raised because of unexpected timeout in running test server support code."""
