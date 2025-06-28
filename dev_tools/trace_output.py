from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional
import json

from dev_tools.trace_data import SaveEvent, NodeState, TestSection, TestTraceData
from dev_tools.trace_shorthand import NodeStateFormat
from dev_tools.trace_formatters import CSVFullFormatter, OrgFormatter, RstFormatter, PUMLFormatter
from dev_tools.feature_db import FeatureDB
from dev_tools.features import registry as feature_regy

class TraceOutput:

    def __init__(self, test_data: TestTraceData):
        self.test_data = test_data
        self.trace_filter = TableTraceFilter()
        self.condensed_sections = []
        self.filtered = None

    def set_trace_filter(self, trace_filter):
        self.trace_filter = trace_filter
                
    def get_table_events(self):
        if self.filtered:
            return self.filtered
        # If the test called end_subtest for each section, they
        # will all have end_pos set, else the last one
        last_section = self.test_data.last_section()
        if last_section.end_pos is None:
            last_section.end_pos = len(self.trace_lines) - 1
        results = {}
        keys = list(self.test_data.test_sections.keys())
        keys.sort()
        for key in keys:
            section = self.test_data.test_sections[key]
            section.count_nodes(self.test_data.trace_lines)
            show = self.trace_filter.filter_events(self.test_data.trace_lines, section.start_pos, section.end_pos)
            # we can use the "start_pos" property of a section
            # as an ID, as it will be unique
            results[section.start_pos] = show
        self.filtered = results
        return self.filtered

    def filter_and_shorten_trace(self):
        lines = []
        keys = list(self.test_sections.keys())
        keys.sort()
        for key in keys:
            section = self.test_data.test_sections[key]
            short = self.make_shorthand_table(section)
            lines.extend(short)
        return lines
        
    def filter_trace(self):
        lines = []
        for sec_lines in self.get_table_events().values():
            for pos in sec_lines:
                lines.append(self.test_data.trace_lines[pos])
        return lines
        
    def write_csv_file(self, filepath, digest=False):
        if not digest:
            formatter = CSVFullFormatter(self.test_data.trace_lines)
        else:
            formatter = CSVFullFormatter(self.filter_trace())
            
        csv_lines = formatter.to_csv()
        if len(csv_lines) > 1:
            with open(filepath, 'w') as f:
                for line in csv_lines:
                    outline = ','.join(line)
                    f.write(outline + "\n")

    def write_org_file(self, filepath, include_legend=True):
        if include_legend:
            prefix = "org"
        else:
            prefix = "no_legend_org"
        org_lines = OrgFormatter(self).format(include_legend)
        if len(org_lines) > 0:
            with open(filepath, 'w') as f:
                for line in org_lines:
                    f.write(line + "\n")

    def write_rst_file(self, filepath):
        org_lines = RstFormatter(self).format()
        if len(org_lines) > 0:
            with open(filepath, 'w') as f:
                for line in org_lines:
                    f.write(line + "\n")

    def write_section_puml_file(self, section, filepath):
        puml = PUMLFormatter(self).format(section)
        if len(puml) > 0:
            with open(filepath, 'w') as f:
                for line in puml:
                    f.write(line + "\n")
        
    def write_json_file(self, filepath):
        rdata = json.dumps(self.test_data, default=lambda o:o.__dict__, indent=4)
        with open(filepath, 'w') as f:
            f.write(rdata)
            
    def write_verbose_trace_file(self, filepath):
        outlines = []
        state_history = {}
        for line in self.test_data.trace_lines:
            out_line = []
            for node_index,ns in enumerate(line):
                prev_state = state_history.get(node_index, None)
                nsf = NodeStateFormat(ns, prev_state)
                out_line.append(nsf.format())
                state_history[node_index] = ns
            outlines.append(out_line)
        with open(filepath, 'w') as f:
            for index,ol in enumerate(outlines):
                f.write(f'- {index} -\n')
                for ni in ol:
                    f.write(f"{ni}\n")
    @classmethod
    def from_json_file(cls, filepath):
        with open(filepath, 'r') as f:
            buff = f.read()

        in_data = json.loads(buff)

        lines = []
        for inline in in_data['trace_lines']:
            outline = []
            for item in inline:
                outline.append(NodeState.from_dict(item))
            lines.append(outline)
        sections = {}
        for pos,insection in in_data['test_sections'].items():
            sections[int(pos)] = TestSection(**insection)

        td = TestTraceData(in_data['test_name'],
                           in_data['test_path'],
                           in_data['test_doc_string'],
                           lines=lines, sections=sections)
        return cls(td)
            
class TableTraceFilter:
    """
    Processes trace_lines and decides which event lines
    should be included in table output forms, which
    may also be used for diagrams.
    """
    
    def __init__(self):
        pass
    
    def filter_events(self, trace_lines, start_pos, end_pos):
        """Filter trace lines to determine which events should be shown in condensed output"""
        events_to_show = []
        for section_pos, line in enumerate(trace_lines[start_pos: end_pos + 1]):
            full_pos = section_pos + start_pos # position in full trace stack
            # we always want firstline in section
            if section_pos == 0:
                events_to_show.append(full_pos)
                continue
            for index, ns in enumerate(line):
                if ns.save_event is not None:
                    if ns.save_event == SaveEvent.message_op:
                        # we are only going to show message trace if the
                        # condition is sent or handled
                        if ns.message_action in ("sent", "handled_in"):
                            events_to_show.append(full_pos)
                    else:
                        events_to_show.append(full_pos)
        return events_to_show


