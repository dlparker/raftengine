from pathlib import Path
from dev_tools.trace_data import decode_message, SaveEvent
from dev_tools.trace_shorthand import NodeStateShortestFormat

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
    """
    New version of OrgFormatter that uses NodeStateShortestFormat instead of legacy Shorthand.
    Produces identical output to the original OrgFormatter.
    """

    def __init__(self, trace_output):
        self.trace_output = trace_output

    def format(self, include_legend=True):
        """Format trace output as .org tables using NodeStateShortestFormat"""
        filter_sections = self.trace_output.get_table_events()
        all_rows = []
        
        # Header section (identical to original)
        all_rows.append(f"* Test {self.trace_output.test_data.test_name} from file {self.trace_output.test_data.test_path}")
        all_rows.append("")
        all_rows.append(self.trace_output.test_data.test_doc_string)
        all_rows.append("")
                
        if include_legend:
            all_rows.append("")
            all_rows.append(" *[[condensed Trace Table Legend][Table legend]] located after last table in file*")
            all_rows.append("")

        # Process each section
        for start_pos, filtered in filter_sections.items():
            section = self.trace_output.test_data.test_sections[start_pos]
            condensed_table = self.make_new_shorthand_table(section)
            
            # Build table with same structure as original
            max_chars = 0
            trows = []
            trows.append(f"** {section.description}")
            
            # Create headers (identical to original)
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
                hrow.append('Role')
                hrow.append('Op')
                hrow.append('Delta')
            hrows.append(hrow)

            # Calculate column widths
            col_widths = [len(col) for col in hrow]
            
            for row in hrows:
                for col_index, col in enumerate(row):
                    col_widths[col_index] = max(col_widths[col_index], len(str(col)))
            
            for row in condensed_table:
                for col_index, col in enumerate(row):
                    col_widths[col_index] = max(col_widths[col_index], len(str(col)))
            
            # Format header rows
            str_line = '|'
            for col_index, col in enumerate(hrows[0]):
                str_line += f" {col:{col_widths[col_index]}s} |"
            trows.append(str_line)
            
            str_line = '|'
            for col_index, col in enumerate(hrows[1]):
                str_line += f" {col:{col_widths[col_index]}s} |"
            trows.append(str_line)
            
            # Format data rows
            for row in condensed_table:
                str_line = "|"
                for col_index, col in enumerate(row):
                    str_line += f" {col:{col_widths[col_index]}s} |"
                trows.append(str_line)
                max_chars = max(max_chars, len(str_line))
            
            # Add separators (identical to original)
            trows.append('-' * max_chars)
            final_rows = [trows[0],]
            final_rows.append('-' * max_chars)
            final_rows.extend(trows[1:])
            all_rows.extend(final_rows)

        # Add legend if requested (identical to original)
        if include_legend:
            legend_path = Path(Path(__file__).parent, "table_legend.org")
            with open(legend_path, 'r') as f:
                buff = f.read()
            for lline in buff.split('\n'):
                all_rows.append(lline)
                
        return all_rows

    def make_new_shorthand_table(self, section):
        """
        Replace trace_output.make_shorthand_table() using NodeStateShortestFormat.
        Returns same table structure as legacy version.
        """
        # Get filtered indices using same logic as legacy
        filter_sections = self.trace_output.get_table_events()
        if section.start_pos not in filter_sections:
            return []
        
        filtered_indices = filter_sections[section.start_pos]
        
        # Convert indices to actual trace lines (same as legacy does)
        filtered_trace = []
        for index in filtered_indices:
            filtered_trace.append(self.trace_output.test_data.trace_lines[index])
        
        # Track state history for each node
        state_histories = {}
        table_rows = []
        
        for trace_line in filtered_trace:
            row_cols = []
            
            # Process each node in this trace line
            for node_index, node_state in enumerate(trace_line):
                prev_state = state_histories.get(node_index, None)
                
                # Use NodeStateShortestFormat instead of legacy Shorthand
                nsf = NodeStateShortestFormat(node_state, prev_state)
                data = nsf.format()
                
                # Extract role, op, delta in same format as legacy
                role = data['role'] or ''
                op = data['op'] or ''
                delta = self.format_delta_string(data['delta'])
                
                # Add the 3 columns for this node (Role, Op, Delta)
                row_cols.extend([role, op, delta])
                
                # Update state history
                state_histories[node_index] = node_state
            
            table_rows.append(row_cols)
        
        return table_rows

    def format_delta_string(self, delta_dict):
        """
        Convert delta dictionary to legacy format string.
        
        Input: {"term": "t-1", "log_last_term": "lt-1", "last_index": "li-1", "commit_index": "", "network_id": ""}
        Output: "t-1 lt-1 li-1" (space-separated, empty values filtered out)
        """
        # Extract non-empty values in consistent order
        items = []
        for key in ["term", "log_last_term", "last_index", "commit_index", "network_id"]:
            value = delta_dict.get(key, "")
            if value and value.strip():
                items.append(value)
        
        return " ".join(items)

class RstFormatter:
    """
    New version of RstFormatter that uses NodeStateShortestFormat instead of legacy Shorthand.
    Produces identical output to the original RstFormatter.
    """

    def __init__(self, trace_output):
        self.trace_output = trace_output

    def format(self):
        """Format trace output as RST tables using NodeStateShortestFormat"""
        filter_sections = self.trace_output.get_table_events()
        all_rows = []
        
        # Header section (identical to original RST format)
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

        # Process each section
        for start_pos, filtered in filter_sections.items():
            section = self.trace_output.test_data.test_sections[start_pos]
            condensed_table = self.make_new_shorthand_table(section)
            
            # Section header
            all_rows.append(f"{section.description}".rstrip('\n'))
            all_rows.append("_"*len(section.description))
            all_rows.append("")
            
            # Features section (if present)
            if section.features:
                for feature in section.features['used']:
                    all_rows.append(f"Raft feature used: {str(feature)}")
                for feature in section.features['tested']:
                    all_rows.append(f"Raft feature tested: {str(feature)}")
                all_rows.append("")
                all_rows.append("")
            
            # Create headers (same as original)
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
                hrow.append('Role')
                hrow.append('Op')
                hrow.append('Delta')
            hrows.append(hrow)

            # Calculate column widths
            col_widths = [len(col) for col in hrow]
            
            for row in hrows:
                for col_index, col in enumerate(row):
                    col_widths[col_index] = max(col_widths[col_index], len(str(col)))
            
            for row in condensed_table:
                for col_index, col in enumerate(row):
                    col_widths[col_index] = max(col_widths[col_index], len(str(col)))
            
            # Build RST table borders
            liner = "+"
            for cindex, cwidth in enumerate(col_widths):
                liner += "-"*(cwidth+2)
                liner += "+"
            divider = "+"
            for cindex, cwidth in enumerate(col_widths):
                divider += "="*(cwidth+2)
                divider += "+"

            # Format table rows
            trows = []
            
            # Upper header row (node names)
            str_line = '|'
            for col_index, col in enumerate(hrows[0]):
                str_line += f" {col:{col_widths[col_index]}s} |"
            trows.append(str_line)
            
            # Lower header row (Role/Op/Delta)
            str_line = '|'
            for col_index, col in enumerate(hrows[1]):
                str_line += f" {col:{col_widths[col_index]}s} |"
            trows.append(str_line)
            
            # Data rows
            for row in condensed_table:
                str_line = "|"
                for col_index, col in enumerate(row):
                    str_line += f" {col:{col_widths[col_index]}s} |"
                trows.append(str_line)
            
            # Assemble table with proper RST borders
            for index, row in enumerate(trows):
                if index == 2:
                    all_rows.append(divider)  # Separator after headers
                else:
                    all_rows.append(liner)    # Regular borders
                all_rows.append(row)
            all_rows.append(liner)  # Final border
            all_rows.append("")
            all_rows.append("")
            all_rows.append("")
            
        return all_rows

    def make_new_shorthand_table(self, section):
        """
        Replace trace_output.make_shorthand_table() using NodeStateShortestFormat.
        Returns same table structure as legacy version.
        """
        # Get filtered indices using same logic as legacy
        filter_sections = self.trace_output.get_table_events()
        if section.start_pos not in filter_sections:
            return []
        
        filtered_indices = filter_sections[section.start_pos]
        
        # Convert indices to actual trace lines (same as legacy does)
        filtered_trace = []
        for index in filtered_indices:
            filtered_trace.append(self.trace_output.test_data.trace_lines[index])
        
        # Track state history for each node
        state_histories = {}
        table_rows = []
        
        for trace_line in filtered_trace:
            row_cols = []
            
            # Process each node in this trace line
            for node_index, node_state in enumerate(trace_line):
                prev_state = state_histories.get(node_index, None)
                
                # Use NodeStateShortestFormat instead of legacy Shorthand
                nsf = NodeStateShortestFormat(node_state, prev_state)
                data = nsf.format()
                
                # Extract role, op, delta in same format as legacy
                role = data['role'] or ''
                op = data['op'] or ''
                delta = self.format_delta_string(data['delta'])
                
                # Add the 3 columns for this node (Role, Op, Delta)
                row_cols.extend([role, op, delta])
                
                # Update state history
                state_histories[node_index] = node_state
            
            table_rows.append(row_cols)
        
        return table_rows

    def format_delta_string(self, delta_dict):
        """
        Convert delta dictionary to legacy format string.
        
        Input: {"term": "t-1", "log_last_term": "lt-1", "last_index": "li-1", "commit_index": "", "network_id": ""}
        Output: "t-1 lt-1 li-1" (space-separated, empty values filtered out)
        """
        # Extract non-empty values in consistent order
        items = []
        for key in ["term", "log_last_term", "last_index", "commit_index", "network_id"]:
            value = delta_dict.get(key, "")
            if value and value.strip():
                items.append(value)
        
        return " ".join(items)


class PUMLFormatter:
    """
    Newm version of PUMLFormatter that uses NodeStateShortestFormat for consistent message processing.
    Produces identical PlantUML output to the original PUMLFormatter.
    """

    def __init__(self, trace_output):
        self.trace_output = trace_output

    def format(self, section):
        """
        Generate PlantUML sequence diagram lines from trace_lines using NodeStateShortestFormat.
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

        # Track unique nodes (same as legacy)
        nodes = set()
        for line in self.trace_output.test_data.trace_lines[section.start_pos:section.end_pos+1]:
            for ns in line:
                nodes.add(ns.uri)
        nodes = sorted(nodes)  # e.g., ['mcpy://1', 'mcpy://2', 'mcpy://3']
        for i, uri in enumerate(nodes, 1):
            puml.append(f'participant "Node {i} (N-{i})" as n{i} order {i*10} #Lightgreen')

        # Track phases and states (same as legacy)
        current_phase = None
        role_changes = {uri: "FOLLOWER" for uri in nodes}
        state = {uri: {"t": 0, "li": 0, "lt": 0, "ci": 0} for uri in nodes}
        
        # Track state history for NodeStateShortestFormat
        state_histories = {}

        # Collect all events first for repetition detection
        all_events = []
        
        # Process events using modernized approach
        for line_idx, line in enumerate(self.trace_output.test_data.trace_lines[section.start_pos:section.end_pos+1]):
            # Process node states
            for node_index, ns in enumerate(line):
                node_id = ns.uri.split("/")[-1]
                node_alias = f"n{node_id}"
                
                # Get previous state for this node
                prev_state = state_histories.get(node_index, None)

                # Role change (same logic as legacy)
                if ns.save_event == SaveEvent.role_changed and ns.role_name != role_changes[ns.uri]:
                    event = {
                        'type': 'role_change',
                        'line': f'{node_alias} -> {node_alias}: NEW ROLE ({ns.role_name})',
                        'note': f'note left of {node_alias}: Role: {role_changes[ns.uri]} → {ns.role_name}',
                        'pattern': f'role_change_{node_alias}_{ns.role_name}'
                    }
                    all_events.append(event)
                    role_changes[ns.uri] = ns.role_name

                # Message operation using NodeStateShortestFormat
                if ns.save_event == SaveEvent.message_op and ns.message_action in ("sent", "handled_in"):
                    msg = ns.message
                    sender_id = msg.sender.split("/")[-1]
                    receiver_id = msg.receiver.split("/")[-1]
                    sender_alias = f"n{sender_id}"
                    receiver_alias = f"n{receiver_id}"

                    # Use NodeStateShortestFormat to get consistent message formatting
                    nsf = NodeStateShortestFormat(ns, prev_state)
                    formatted_data = nsf.format()
                    
                    # Convert the formatted op to PlantUML syntax
                    if formatted_data['op']:
                        puml_line = self.convert_shorthand_to_puml(formatted_data['op'], sender_alias, receiver_alias, msg)
                        if puml_line:
                            # Extract message type for pattern matching
                            msg_type = self.extract_message_type(puml_line)
                            event = {
                                'type': 'message',
                                'line': puml_line,
                                'pattern': f'{msg_type}_{sender_alias}_{receiver_alias}',
                                'msg_type': msg_type,
                                'sender': sender_alias,
                                'receiver': receiver_alias
                            }
                            all_events.append(event)

                # State changes (modernized using NodeStateShortestFormat delta)
                if prev_state is not None:
                    nsf = NodeStateShortestFormat(ns, prev_state)
                    formatted_data = nsf.format()
                    delta = formatted_data['delta']
                    
                    # Check for state changes using delta
                    if delta.get('last_index'):
                        li_value = delta['last_index'].replace('li-', '') if delta['last_index'] else '0'
                        lt_value = delta['log_last_term'].replace('lt-', '') if delta.get('log_last_term') else '0'
                        event = {
                            'type': 'state_change',
                            'line': f'note {"left" if node_id == "1" else "right"} of {node_alias}: Last Index: li-{li_value}; Last Term: lt-{lt_value}',
                            'pattern': f'last_index_{node_alias}'
                        }
                        all_events.append(event)
                    
                    if delta.get('commit_index'):
                        ci_value = delta['commit_index'].replace('ci-', '') if delta['commit_index'] else '0'
                        event = {
                            'type': 'state_change',
                            'line': f'note {"left" if node_id == "1" else "right"} of {node_alias}: Commit Index: ci-{ci_value}',
                            'pattern': f'commit_index_{node_alias}'
                        }
                        all_events.append(event)
                    
                    if delta.get('term'):
                        t_value = delta['term'].replace('t-', '') if delta['term'] else '0'
                        event = {
                            'type': 'state_change',
                            'line': f'note {"left" if node_id == "1" else "right"} of {node_alias}: Term: t-{t_value}',
                            'pattern': f'term_{node_alias}'
                        }
                        all_events.append(event)

                # Update state history
                state_histories[node_index] = ns
        
        # Detect and condense repetitions
        condensed_events = self.condense_repetitions(all_events)
        
        # Add condensed events to PUML
        for event in condensed_events:
            if event['type'] == 'role_change':
                puml.append(event['line'])
                if 'note' in event:
                    puml.append(event['note'])
            elif event['type'] == 'condensed_repetition':
                puml.extend(event['lines'])
            else:
                puml.append(event['line'])

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

    def convert_shorthand_to_puml(self, shorthand_op, sender_alias, receiver_alias, msg):
        """
        Convert NodeStateShortestFormat operation string to PlantUML sequence diagram syntax.
        
        Input: "ae+N-2 t-1 i-0 lt-0 e-1 c-0" or "N-1+ae_reply ok-True mi-1"
        Output: "n1 -> n2: ae t-1 i-0 lt-0 e-1 c-0"
        """
        if not shorthand_op:
            return None

        # Parse the shorthand operation
        if '+' not in shorthand_op:
            return None
            
        parts = shorthand_op.split(' ', 1)
        direction_part = parts[0]
        params_part = parts[1] if len(parts) > 1 else ""
        
        # Determine direction and message type
        if direction_part.startswith('N-'):
            # Incoming message: "N-1+ae_reply" -> sender to receiver
            direction = f"{sender_alias} -> {receiver_alias}"
            msg_type = direction_part.split('+')[1]
        else:
            # Outgoing message: "ae+N-2" -> sender to receiver  
            direction = f"{sender_alias} -> {receiver_alias}"
            msg_type = direction_part.split('+')[0]
        
        # Map message types to PlantUML display
        msg_display_map = {
            'ae': 'ae',
            'ae_reply': 'ae_reply', 
            'poll': 'poll',
            'vote': 'vote',
            'p_v_r': 'p_v_r',
            'p_v': 'p_v',
            'm_c': 'm_c',
            'm_cr': 'm_cr',
            't_p': 't_p',
            't_pr': 't_pr',
            'sn': 'sn',
            'snr': 'snr'
        }
        
        display_type = msg_display_map.get(msg_type, msg_type)
        
        # Build final PlantUML line
        if params_part:
            return f"{direction}: {display_type} {params_part}"
        else:
            return f"{direction}: {display_type}"

    def extract_message_type(self, puml_line):
        """Extract message type from PlantUML line for pattern matching"""
        # Example: "n1 -> n2: ae t-1 i-0 lt-0 e-1 c-0" -> "ae"
        if ': ' in puml_line:
            content = puml_line.split(': ', 1)[1]
            return content.split(' ')[0]
        return "unknown"

    def condense_repetitions(self, events, min_repetitions=3):
        """
        Detect and condense repeated message patterns.
        
        Args:
            events: List of event dictionaries
            min_repetitions: Minimum number of repetitions to condense
            
        Returns:
            List of condensed events
        """
        if len(events) < min_repetitions:
            return events
        
        condensed = []
        i = 0
        
        while i < len(events):
            current_event = events[i]
            
            # Only condense message events
            if current_event['type'] != 'message':
                condensed.append(current_event)
                i += 1
                continue
            
            # Look for repeated patterns
            repetition_info = self.find_repetition_sequence(events, i, min_repetitions)
            
            if repetition_info:
                # Found a repetition sequence
                start_idx, end_idx, pattern, count = repetition_info
                first_event = events[start_idx]
                last_event = events[end_idx - 1]
                
                # Create condensed representation
                condensed_event = {
                    'type': 'condensed_repetition',
                    'lines': [
                        first_event['line'],
                        f"note over {first_event['sender']}, {first_event['receiver']}: ... {count-2} more {first_event['msg_type']} messages ...",
                        last_event['line']
                    ]
                }
                condensed.append(condensed_event)
                i = end_idx
            else:
                # No repetition, keep original event
                condensed.append(current_event)
                i += 1
        
        return condensed

    def find_repetition_sequence(self, events, start_idx, min_repetitions):
        """
        Find if there's a repeated sequence starting at start_idx.
        
        Returns:
            Tuple of (start_idx, end_idx, pattern, count) if repetition found, None otherwise
        """
        if start_idx >= len(events):
            return None
        
        base_pattern = events[start_idx]['pattern']
        count = 1
        
        # Count consecutive events with same pattern
        for i in range(start_idx + 1, len(events)):
            if (events[i]['type'] == 'message' and 
                events[i]['pattern'] == base_pattern):
                count += 1
            else:
                break
        
        if count >= min_repetitions:
            return (start_idx, start_idx + count, base_pattern, count)
        
        return None
