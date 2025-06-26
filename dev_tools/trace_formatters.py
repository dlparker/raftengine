from pathlib import Path
from dev_tools.trace_data import decode_message, SaveEvent

class CSVFullFormatter:

    def __init__(self, trace_lines):
        self.trace_lines = trace_lines

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
        cols.append('elapsed_time')
        # we need to know the max nodes at any point during the test, as it can change
        max_nodes = 0
        for line in self.trace_lines:
            max_nodes = max(max_nodes, len(line))
        for i in range(1, max_nodes + 1):
            cols.append(f'n{i}-uri')
            cols.append(f'n{i}-role')
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
                        # if the trace is live in memory, we have actual
                        # messages. If read from file, we have json dicts of the messages
                        if isinstance(ns.message, dict):
                            ns.message = decode_message(ns.message)
                        cols.append(ns.message.sender)
                        cols.append(ns.message.receiver)
                        cols.append(str(ns.message_action))
                        cols.append(ns.message.code)
                        if ns.message.code == "append_entries":
                            cols.append(f'{len(ns.message.entries)}')
                            cols.append(f'{ns.message.commitIndex}')
                            cols.append('')
                            cols.append('')
                            if ns.elapsed_time:
                                cols.append(f'{ns.elapsed_time:8.8f}')
                            else:
                                cols.append('')
                        elif ns.message.code == "append_response":
                            cols.append('')
                            cols.append('')
                            cols.append(f'{ns.message.success}')
                            cols.append(f'{ns.message.maxIndex}')
                            if ns.elapsed_time:
                                cols.append(f'{ns.elapsed_time:8.8f}')
                            else:
                                cols.append('')
                        else:
                            cols.append('')
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
                        cols.append('')
                    break
            for index,ns in enumerate(line):
                if f"mcpy://{index + 1}" != ns.uri:
                    raise Exception('damn')
                cols.append(ns.uri)
                cols.append(str(ns.role_name))
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

class OrgFormatter:

    def __init__(self, trace_output):
        self.trace_output = trace_output

    def format(self, include_legend=True):
        filter_sections = self.trace_output.get_table_events()
        all_rows = []
        all_rows.append(f"* Test {self.trace_output.test_data.test_name} from file {self.trace_output.test_data.test_path}")
        all_rows.append("")
        all_rows.append(self.trace_output.test_data.test_doc_string)
        all_rows.append("")
                
        if include_legend:
            all_rows.append("")
            all_rows.append(" *[[condensed Trace Table Legend][Table legend]] located after last table in file*")
            all_rows.append("")

        for start_pos, filtered in filter_sections.items():
            section = self.trace_output.test_data.test_sections[start_pos]
            condensed_table = self.trace_output.make_shorthand_table(section)
            max_chars = 0
            trows = []
            trows.append(f"** {section.description}")
            hrows = []
            hrow = []
            for index in range(section.max_nodes):
                data = f'N-{index+1}'
                hrow.append(data)
                hrow.append(data)
                hrow.append(data)
            hrows.append(hrow)
            hrow = []
            for index in range(section.max_nodes):
                col = 'Role'
                hrow.append(col)
                col = 'Op'
                hrow.append(col)
                col = 'Delta'
                hrow.append(col)
            # get the column widths
            col_widths = [len(col) for col in hrow ]
            hrows.append(hrow)

            for row in hrows:
                for col_index, col in enumerate(row):
                    col_widths[col_index] = max(col_widths[col_index], len(str(col)))
            for row in condensed_table:
                for col_index, col in enumerate(row):
                    col_widths[col_index] = max(col_widths[col_index], len(str(col)))
            # insert three upper header items with node name
            str_line = '|'
            for col_index, col in enumerate(hrows[0]):
                str_line += f" {col:{col_widths[col_index]}s} |"
            trows.append(str_line)
            str_line = '|'
            # insert the three lower header items
            for col_index, col in enumerate(hrows[1]):
                str_line += f" {col:{col_widths[col_index]}s} |"
            trows.append(str_line)
            
            for row in condensed_table:
                str_line = "|"
                for col_index, col in enumerate(row):
                    str_line += f" {col:{col_widths[col_index]}s} |"
                trows.append(str_line)
                max_chars = max(max_chars, len(str_line))
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
    
class RstFormatter:

    def __init__(self, trace_output):
        self.trace_output = trace_output

    def format(self):
        filter_sections = self.trace_output.get_table_events()
        all_rows = []
        all_rows.append(f".. _{self.trace_output.test_data.test_name}:")
        s1 = f"Test {self.trace_output.test_data.test_name} from file {self.trace_output.test_data.test_path}"
        all_rows.append(s1)
        all_rows.append("="*len(s1))
        all_rows.append("")
        all_rows.append(self.trace_output.test_data.test_doc_string)
        all_rows.append("")
                
        all_rows.append("")
        all_rows.append("- See :ref:`Trace Table Legend` for help interpreting table contents")
        all_rows.append("")

        for start_pos, filtered in filter_sections.items():
            section = self.trace_output.test_data.test_sections[start_pos]
            condensed_table = self.trace_output.make_shorthand_table(section)
            max_chars = 0
            trows = []
            all_rows.append(f"{section.description}".rstrip('\n'))
            all_rows.append("_"*len(section.description))
            all_rows.append("")
            if section.features:
                for feature in section.features['used']:
                    all_rows.append(f"Raft feature used: {str(feature)}")
                for feature in section.features['tested']:
                    all_rows.append(f"Raft feature tested: {str(feature)}")
                all_rows.append("")
                all_rows.append("")
            hrows = []
            hrow = []
            for index in range(section.max_nodes):
                data = f'N-{index+1}'
                hrow.append(data)
                hrow.append(data)
                hrow.append(data)
            col_count = len(hrow)
            hrows.append(hrow)
            hrow = []
            for index in range(section.max_nodes):
                col = 'Role'
                hrow.append(col)
                col = 'Op'
                hrow.append(col)
                col = 'Delta'
                hrow.append(col)
            # get the column widths
            col_widths = [len(col) for col in hrow ]
            hrows.append(hrow)
            for row in hrows:
                for col_index, col in enumerate(row):
                    col_widths[col_index] = max(col_widths[col_index], len(str(col)))
            for row in condensed_table:
                for col_index, col in enumerate(row):
                    col_widths[col_index] = max(col_widths[col_index], len(str(col)))
            liner = "+"
            for cindex, cwidth in enumerate(col_widths):
                liner += "-"*(cwidth+2)
                liner += "+"
            divider = "+"
            for cindex, cwidth in enumerate(col_widths):
                divider += "="*(cwidth+2)
                divider += "+"

            # insert three upper header items with node name
            str_line = '|'
            for col_index, col in enumerate(hrows[0]):
                str_line += f" {col:{col_widths[col_index]}s} |"
            trows.append(str_line)
            str_line = '|'
            # insert the three lower header items
            for col_index, col in enumerate(hrows[1]):
                str_line += f" {col:{col_widths[col_index]}s} |"
            trows.append(str_line)
            
            for row in condensed_table:
                str_line = "|"
                for col_index, col in enumerate(row):
                    str_line += f" {col:{col_widths[col_index]}s} |"
                trows.append(str_line)
            for index, row in enumerate(trows):
                if index == 2:
                    all_rows.append(divider)
                else:
                    all_rows.append(liner)
                all_rows.append(row)
            all_rows.append(liner)
            all_rows.append("")
            all_rows.append("")
            all_rows.append("")
        return all_rows
    
class PUMLFormatter:

    def __init__(self, trace_output):
        self.trace_output = trace_output

    def format(self, section):
        """
        Generate PlantUML sequence diagram lines from trace_lines.
        """
        puml = [
            "@startuml",
            "!pragma ratio 0.7",
            "skinparam dpi 150",
            "skinparam monochrome false",
            "skinparam sequence {",
            "  ArrowColor Black",
            "  ActorBorderColor Black",
            "  LifeLineBorderColor Black",
            "  ParticipantFontSize 12",
            "  Padding 10",
            "}",
            "skinparam legend {",
            "  BackgroundColor #F5F5F5",
            "  FontSize 11",
            "}",
            f'title PreVote Election Sequence ({self.trace_output.test_data.test_name})',
            ""
        ]

        # Track unique nodes
        nodes = set()
        for line in self.trace_output.test_data.trace_lines[section.start_pos:section.end_pos+1]:
            for ns in line:
                nodes.add(ns.uri)
        nodes = sorted(nodes)  # e.g., ['mcpy://1', 'mcpy://2', 'mcpy://3']
        for i, uri in enumerate(nodes, 1):
            puml.append(f'participant "Node {i} (N-{i})" as n{i} order {i*10} #Lightgreen')

        # Track phases and states
        current_phase = None
        role_changes = {uri: "FOLLOWER" for uri in nodes}
        state = {uri: {"t": 0, "li": 0, "lt": 0, "ci": 0} for uri in nodes}
        # phase_map not currently used, will consider basing it on raft features stuff
        use_phase_map = False
        if use_phase_map:
            phase_map = {
                "Testing election with pre-vote enabled": "PreVote Phase",
                "Node 1 is now leader": "Voting Phase",
                "Node 1 should get success replies": "TERM_START Propagation"
            }

        # Process events
        for line_idx, line in enumerate(self.trace_output.test_data.trace_lines[section.start_pos:section.end_pos+1]):
            if use_phase_map:
                # Determine phase from test_rec.sections
                phase = None
                for pos, section in self.self.trace_output.test_data.test_sections.items():
                    if section.start_pos <= line_idx <= (section.end_pos or float('inf')):
                        phase = phase_map.get(section.description, section.description)
                        break
                if phase and phase != current_phase:
                    puml.append("")
                    puml.append(f"== {phase} ==")
                    current_phase = phase
            # Process node states
            for ns in line:
                node_id = ns.uri.split("/")[-1]
                node_alias = f"n{node_id}"

                # Role change
                if ns.save_event == SaveEvent.role_changed and ns.role_name != role_changes[ns.uri]:
                    puml.append(f'{node_alias} -> {node_alias}: NEW ROLE ({ns.role_name})')
                    puml.append(f'note left of {node_alias}: Role: {role_changes[ns.uri]} → {ns.role_name}')
                    role_changes[ns.uri] = ns.role_name

                # Message operation
                if ns.save_event == SaveEvent.message_op and ns.message_action in ("sent", "handled_in"):
                    msg = ns.message
                    sender_id = msg.sender.split("/")[-1]
                    receiver_id = msg.receiver.split("/")[-1]
                    sender_alias = f"n{sender_id}"
                    receiver_alias = f"n{receiver_id}"

                    if msg.code == "pre_vote":
                        puml.append(f'{sender_alias} -> {receiver_alias}: p_v_r t-{msg.term} li-{msg.prevLogIndex} lt-{msg.prevLogTerm}')
                    elif msg.code == "pre_vote_response":
                        puml.append(f'{sender_alias} -> {receiver_alias}: p_v yes-{msg.vote}')
                    elif msg.code == "request_vote":
                        puml.append(f'{sender_alias} -> {receiver_alias}: poll t-{msg.term} li-{msg.prevLogIndex} lt-{msg.prevLogTerm}')
                    elif msg.code == "request_vote_response":
                        puml.append(f'{sender_alias} -> {receiver_alias}: vote yes-{msg.vote}')
                    elif msg.code == "append_entries":
                        puml.append(f'{sender_alias} -> {receiver_alias}: ae t-{msg.term} i-{msg.prevLogIndex} lt-{msg.prevLogTerm} e-{len(msg.entries)} c-{msg.commitIndex}')
                    elif msg.code == "append_response":
                        puml.append(f'{sender_alias} -> {receiver_alias}: ae_reply ok-{msg.success} mi-{msg.maxIndex}')
                    elif msg.code == "membership_change":
                        puml.append(f'{sender_alias} -> {receiver_alias}: m_c op-{msg.op} n-{msg.target_uri.split("/")[-1]}')
                    elif msg.code == "membership_change_response":
                        puml.append(f'{sender_alias} -> {receiver_alias}: m_cr ok-{msg.ok}')
                    elif msg.code == "transfer_power":
                        puml.append(f'{sender_alias} -> {receiver_alias}: t_p i-{msg.prevLogIndex}')
                    elif msg.code == "transfer_power_response":
                        puml.append(f'{sender_alias} -> {receiver_alias}: t_pr ok-{msg.success}')
                    elif msg.code == "snapshot":
                        puml.append(f'{sender_alias} -> {receiver_alias}: sn i-{msg.prevLogIndex}')
                    elif msg.code == "snapshot_response":
                        puml.append(f'{sender_alias} -> {receiver_alias}: snr s-{msg.success}')

                # State changes
                if ns.log_rec and ns.log_rec.index != state[ns.uri]["li"]:
                    state[ns.uri]["li"] = ns.log_rec.index
                    state[ns.uri]["lt"] = ns.log_rec.term
                    puml.append(f'note {"left" if node_id == "1" else "right"} of {node_alias}: Last Index: li-{state[ns.uri]["li"]}; Last Term: lt-{state[ns.uri]["lt"]}')
                if ns.commit_index != state[ns.uri]["ci"]:
                    state[ns.uri]["ci"] = ns.commit_index
                    puml.append(f'note {"left" if node_id == "1" else "right"} of {node_alias}: Commit Index: ci-{state[ns.uri]["ci"]}')
                if ns.term != state[ns.uri]["t"]:
                    state[ns.uri]["t"] = ns.term
                    puml.append(f'note {"left" if node_id == "1" else "right"} of {node_alias}: Term: t-{state[ns.uri]["t"]}')

        puml.extend([
            "",
            "legend right",
            '  <#GhostWhite,#GhostWhite>|      |= __Legend__ |',
            '  |<#Lightgreen>| Raft Engine Node |',
            '  |FLWR| Follower Role |',
            '  |CNDI| Candidate Role |',
            '  |LEAD| Leader Role |',
            '  |p_v_r| PreVote Request |',
            '  |p_v| PreVote Response |',
            '  |poll| Request Vote |',
            '  |vote| Vote Response |',
            '  |ae| Append Entries (TERM_START) |',
            '  |ae_reply| Append Entries Response |',
            '  |m_c| Membership Change |',
            '  |m_cr| Membership Change Response |',
            '  |t_p| Transfer Power |',
            '  |t_pr| Transfer Power Response |',
            '  |sn| Snapshot |',
            '  |snr| Snapshot Response |',
            "endlegend",
            "@enduml"
        ])

        return puml

