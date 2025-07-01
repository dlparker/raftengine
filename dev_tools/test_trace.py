import os
import inspect
import json
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from raftengine.api.log_api import LogRec
from dev_tools.features import FeatureRegistry
from dev_tools.trace_data import SaveEvent, NodeState, TestSection, TestTraceData
from dev_tools.trace_output import TraceOutput

warn_no_docstring = True

@dataclass
class TestRec:
    test_name: str
    test_path: str 
    description: str
    test_doc_string: str
    start_pos: int
    end_pos: Optional[int] = field(default=None)
    sections: dict[int, TestSection] = field(default_factory=dict)
    condensed_tables: list = field(default=None)

        
    def last_section(self):
        if len(self.sections) < 1:
            return None
        keys = list(self.sections.keys())
        keys.sort()
        return self.sections[keys[-1]]
    

def get_current_test():
    full_name = os.environ.get('PYTEST_CURRENT_TEST').split(' ')[0]
    test_file = full_name.split("::")[0].split('/')[-1].split('.py')[0]
    test_name = full_name.split("::")[1]

    return full_name, test_file, test_name

import inspect

def get_function_from_frame(frame):
    """
    Retrieves the function object associated with a given frame.

    Args:
        frame: The frame object.

    Returns:
        The function object associated with the frame, or None if not found.
    """
    code = frame.f_code
    for name in frame.f_globals:
        obj = frame.f_globals[name]
        if inspect.isfunction(obj) and obj.__code__ is code:
            return obj
    return None

class TestTrace:

    def __init__(self, cluster):
        self.cluster = cluster
        self.node_states = {}
        self.trace_lines = []
        #self.test_sections = {}
        self.test_rec = None
        self.test_logger = None
        self.feature_registry = FeatureRegistry.get_registry()

    async def start(self):
        tl = []
        for uri,node in self.cluster.nodes.items():
            ns = self.node_states[uri] = await self.create_node_state(node)
            tl.append(deepcopy(ns))
            ns.save_event = None
        self.trace_lines.append(tl)

    async def test_done(self):
        if self.test_rec:
            cw = self.test_rec.last_section()
            if cw and cw.start_pos >= len(self.trace_lines):
                del self.test_rec.sections[cw.start_pos]
                return
            if cw and cw.end_pos is None:
                cw.end_pos=len(self.trace_lines)-1
        
    async def add_node(self, node):
        ns = self.node_states[node.uri] = await self.create_node_state(node)

    async def create_node_state(self, node):
        ns = NodeState(save_event=SaveEvent.started,
                       uri=node.uri,
                       log_rec=await node.log.read(),
                       term=await node.log.get_term(),
                       commit_index=await node.log.get_commit_index(),
                       role_name=node.get_role_name(),
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
        ns.role_name = node.get_role_name()
        ns.is_paused = node.am_paused
        ns.is_crashed = node.am_crashed
        ns.leader_id = node.get_leader_id()
        ns.voted_for  = await node.log.get_voted_for()
        return ns

    async def define_test(self, description, logger=None, section_is_prep=True):
        if len(self.trace_lines) > 0:
            raise Exception('must call define_test before starting traced activitities')
        full_name, test_file, test_name = get_current_test()
        frame = inspect.currentframe().f_back
        func = get_function_from_frame(frame)
        doc_string = func.__doc__
        start_pos = 0
        self.test_rec = TestRec(test_name=test_name, test_path=test_file, description=description,
                                   test_doc_string=doc_string, start_pos=start_pos)
        section = TestSection(index=len(self.test_rec.sections),
                              description=description, start_pos=start_pos, is_prep=True)
        fdb = self.feature_registry.feature_db
        fdb.record_test(test_name, test_file, description, doc_string, [])
        self.test_rec.sections[start_pos] = section
        self.test_logger = logger
        if self.test_logger:
            self.test_logger.info("Starting test %s:%s::%s", test_file, test_name, description)
        await self.start()

    async def start_test_prep(self, description, features=None):
        await self.start_subtest(description, features=features, is_prep=True)
        
    async def start_subtest(self, description, features=None, is_prep=False):
        fdb = self.feature_registry.feature_db
        section = self.test_rec.last_section()
        if len(self.trace_lines) > 1:
            if section and section.end_pos is None:
                await self.end_subtest()
            start_pos = len(self.trace_lines)
            section = TestSection(index=len(self.test_rec.sections),
                                  start_pos=start_pos, description=description, is_prep=is_prep)
            self.test_rec.sections[start_pos] = section
        else:
            # We have a special case, when there is a section because we made one
            # in "define_test", but the only event in it is the 'node started' event.
            # In that case we want to just continue with the section, but rename it
            section.description = description
            section.is_prep = is_prep
        fdb.record_test_section(self.test_rec.test_name, self.test_rec.test_path, section)
        section.features = await self.mark_test_features(section, features)
        if self.test_logger:
            if is_prep:
                self.test_logger.info("Preparing test conditions by %s", description)
            else:
                self.test_logger.info("Starting subtest %s", description)

    async def mark_test_features(self, section, features):
        used = []
        tested = []
        if features is None:
            return {'used': [], 'tested': []}
        else:
            for feature in features['used']:
                self.feature_registry.add_test_to_feature(feature, 'uses',
                                                 self.test_rec.test_name, self.test_rec.test_path,
                                                 section)
                used.append(str(feature))
            for feature in features['tested']:
                self.feature_registry.add_test_to_feature(feature, 'tests',
                                                 self.test_rec.test_name, self.test_rec.test_path,
                                                 section)
                tested.append(str(feature))
        return {'used': used, 'tested': tested}

    async def end_subtest(self):
        # Sometimes this gets called on a single, empty section because
        # one was created by define test, but a new section was created
        # before any events were logged.
        #
        section = self.test_rec.last_section()
        section.end_pos = len(self.trace_lines) - 1
        self.test_rec.end_pos = section.end_pos
        if self.test_logger:
            if section.is_prep:
                self.test_logger.info("Done with test prep %s", section.description)
            else:
                self.test_logger.info("Done with subtest %s", section.description)

    async def save_trace_line(self):
        # We write a new trace line for any change to any node, and each
        # trace line records everything about every node.
        # This is not efficient, but it cannot result in confusion about
        # order
        tl = []
        save_event = None
        for uri,node in self.cluster.nodes.items():
            # nodes can get added after startup
            if uri not in self.node_states:
                ns = self.node_states[uri] = await self.create_node_state(node)
                tl.append(deepcopy(ns))
                ns.save_event = None
                tl.append(deepcopy(ns))
            ns = self.node_states[uri]
            ns = await self.update_node_state(node, ns)
            tl.append(deepcopy(ns))
            if ns.save_event and save_event is None:
                save_event = ns.save_event
        self.trace_lines.append(tl)
        if self.test_logger and False:
            self.test_logger.info("event %s", save_event)

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

    async def note_message_handled(self, target, message, elapsed_time):
        ns = self.node_states[target.uri]
        ns.save_event = SaveEvent.message_op
        ns.message = message
        ns.message_action = "handled_in"
        await self.save_trace_line()
        ns.save_event = None
        ns.message = None
        ns.message_action = None
        ns.elapsed_time = elapsed_time

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

    def save_json(self):
        if self.test_rec is None:
            return
        full_name, tfile, test_name = get_current_test()
        x = full_name.split('::')
        test_file_path = Path(x[0])
        test_name = x[1]
        ttd = TestTraceData(self.test_rec.test_name,
                            self.test_rec.test_path,
                            self.test_rec.test_doc_string,
                            self.trace_lines, self.test_rec.sections)
        to = TraceOutput(ttd)
        to.write_json_file()

    def save_features(self):
        trace_dir = Path(Path(__file__).parent.parent.resolve(), "captures", "features")
        if not trace_dir.exists():
            trace_dir.mkdir(parents=True)
        self.feature_registry.save_maps(Path(trace_dir, "maps.json"))
        
        


