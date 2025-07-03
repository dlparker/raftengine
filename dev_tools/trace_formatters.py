from pathlib import Path
from dev_tools.trace_data import decode_message, SaveEvent
from dev_tools.trace_shorthand import NodeStateShortestFormat
from dev_tools.features import FeatureRegistry
from dev_tools.readable_message_formatters import READABLE_MESSAGE_FORMATTERS, ReadableMessageFormat

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
        for index, filtered in filter_sections.items():
            section = self.trace_output.test_data.test_sections[index]
            condensed_table = self.make_new_shorthand_table(section)
            
            # Build table with same structure as original
            max_chars = 0
            trows = []
            all_rows.append(f"** {section.title}")
            if section.description:
                all_rows.append(f"\n{section.description}")
            all_rows.append("")
            all_rows.append("")
            
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
        if section.index not in filter_sections:
            return []
        
        filtered_indices = filter_sections[section.index]
        
        # Convert indices to actual trace lines (same as legacy does)
        filtered_trace = []
        for pos in filtered_indices:
            filtered_trace.append(self.trace_output.test_data.trace_lines[pos])
        
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
        

        all_rows.append(f".. _{self.trace_output.test_data.test_name}:")
        all_rows.append("")
        s1 = f"Test {self.trace_output.test_data.test_name} from file {self.trace_output.test_data.test_path}"
        all_rows.append("="*len(s1))
        all_rows.append(s1)
        all_rows.append("="*len(s1))
        all_rows.append("")
        all_rows.append(self.trace_output.test_data.test_doc_string)
        all_rows.append("")
                
        # Process each section
        for index, filtered in filter_sections.items():
            section = self.trace_output.test_data.test_sections[index]
            if section.start_pos == section.end_pos:
                # empty, ignore it
                continue
            condensed_table = self.make_new_shorthand_table(section)
            
            # Section header
            hline = f"Section {section.index+1}: {section.title}".rstrip('\n')
            all_rows.append(hline)
            all_rows.append("="*len(hline))
            all_rows.append("")
            if section.description:
                all_rows.append(f"\n{section.description}")
            all_rows.append("")
            
            # Features section (if present)
            if section.features:
                for mode in ('tested', 'used'):
                    done = []
                    if section.features[mode]:  # Only add header if there are features
                        all_rows.append(f"Raft features {mode}:\n")
                    for fnum, feature_string in enumerate(section.features[mode]):
                        plist = str(feature_string).split('.')
                        froot = plist[0]
                        regy = FeatureRegistry.get_registry()
                        feature = regy.features[froot]
                        
                        # Add feature documentation for each unique feature
                        if froot not in done:
                            all_rows.append(f".. include:: /developer/tests/features/{feature.get_name_snake()}/short.rst")
                            all_rows.append("")
                            all_rows.append(f".. collapse:: {feature.get_name_snake()} details (click to toggle view)")
                            all_rows.append("")
                            all_rows.append(f"   .. include:: /developer/tests/features/{feature.get_name_snake()}/features.rst")
                            all_rows.append("")
                            all_rows.append(f"   .. include:: /developer/tests/features/{feature.get_name_snake()}/narative.rst")
                            all_rows.append("")
                            all_rows.append("")
                            done.append(froot)
                        cur_path = []
                        for b_name in plist[1:]:
                            cur_path.append(b_name)
                            branch_path = '.'.join(cur_path)
                            if branch_path not in done:
                                branch_key = '.'.join(cur_path)
                                branch = feature.branches[branch_key]
                                partial = f"{feature.get_name_snake()}/branches/{'.'.join(cur_path)}"
                                all_rows.append(f".. include..  :: /developer/tests/features/{partial}/short.rst")
                                all_rows.append("")
                                all_rows.append(f".. collapse:: {partial} details (click to toggle view)")
                                all_rows.append("")
                                all_rows.append(f"   .. include:: /developer/tests/features/{partial}/features.rst")
                                all_rows.append("")
                                all_rows.append(f"   .. include:: /developer/tests/features/{partial}/narative.rst")
                                all_rows.append("")
                                all_rows.append("")
                                done.append(branch_path)
                                done.append(b_name)
                        
                all_rows.append("")
                all_rows.append("")
            
            all_rows.append(f".. collapse:: section {section.index + 1} trace table (click to toggle view)")
            all_rows.append("")
            all_rows.append("   - See :ref:`Trace Table Legend` for help interpreting table contents")
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
                while col_index < len(col_widths) - 1:
                    col_index += 1
                    col = ''
                    str_line += f" {col:{col_widths[col_index]}s} |"
                trows.append(str_line)
            
            # Assemble table with proper RST borders
            spacer = " "*3
            for index, row in enumerate(trows):
                if index == 2:
                    all_rows.append(spacer + divider)  # Separator after headers
                else:
                    all_rows.append(spacer + liner)    # Regular borders
                all_rows.append(spacer + row)
            all_rows.append(spacer + liner)  # Final border
            all_rows.append("")
            all_rows.append("")
            all_rows.append("")
            all_rows.append(f".. collapse:: trace sequence diagram (click to toggle view)")
            all_rows.append("")
            x = f"/developer/tests/diagrams/"
            x += f"{self.trace_output.test_data.test_path}/"
            x += f"{self.trace_output.test_data.test_name}_{section.index + 1}.puml"
            all_rows.append(f"   .. plantuml:: {x}")
            all_rows.append("          :scale: 100%")
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
        if section.index not in filter_sections:
            return []
        
        filtered_indices = filter_sections[section.index]
        
        # Convert indices to actual trace lines (same as legacy does)
        filtered_trace = []
        for pos in filtered_indices:
            filtered_trace.append(self.trace_output.test_data.trace_lines[pos])
        
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
    Enhanced PlantUML formatter that produces human-readable sequence diagrams.
    Uses readable message formatters instead of abbreviated shorthand for better clarity.
    """

    def __init__(self, trace_output):
        self.trace_output = trace_output

    def format(self, section):
        """
        Generate readable PlantUML sequence diagram lines from trace_lines.
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
            f'title Raft Consensus Sequence ({self.trace_output.test_data.test_name} Section {section.index+1})',
            ""
        ]

        # Track unique nodes
        nodes = set()
        for line in self.trace_output.test_data.trace_lines[section.start_pos:section.end_pos+1]:
            for ns in line:
                nodes.add(ns.uri)
        nodes = sorted(nodes)  # e.g., ['mcpy://1', 'mcpy://2', 'mcpy://3']
        for i, uri in enumerate(nodes, 1):
            puml.append(f'participant "Node {i}" as n{i} order {i*10} #Lightgreen')

        # Track phases and states
        role_changes = {uri: "FOLLOWER" for uri in nodes}
        
        # Track state history for message processing  
        state_histories = {}

        # Process events
        for line_idx, line in enumerate(self.trace_output.test_data.trace_lines[section.start_pos:section.end_pos+1]):
            # Process node states
            for node_index, ns in enumerate(line):
                node_id = ns.uri.split("/")[-1]
                node_alias = f"n{node_id}"
                
                # Get previous state for this node
                prev_state = state_histories.get(node_index, None)

                # Role change with descriptive text
                if ns.save_event == SaveEvent.role_changed and ns.role_name != role_changes[ns.uri]:
                    puml.append(f'{node_alias} -> {node_alias}: Becomes {ns.role_name}')
                    role_changes[ns.uri] = ns.role_name

                # Message operation using readable formatters
                if ns.save_event == SaveEvent.message_op and ns.message_action in ("sent"):
                    if isinstance(ns.message, dict):
                        msg = decode_message(ns.message)
                    else:
                        msg = ns.message
                    sender_id = msg.sender.split("/")[-1]
                    receiver_id = msg.receiver.split("/")[-1]
                    sender_alias = f"n{sender_id}"
                    receiver_alias = f"n{receiver_id}"

                    # Use readable message formatter
                    readable_msg = self.format_message_readable(msg, ns)
                    if readable_msg:
                        puml.append(f"{sender_alias} -> {receiver_alias}: {readable_msg}")

                # State changes with descriptive text
                if prev_state is not None:
                    nsf = NodeStateShortestFormat(ns, prev_state)
                    formatted_data = nsf.format()
                    delta = formatted_data['delta']
                    
                    # Generate readable state change notes
                    state_notes = []
                    if delta.get('last_index'):
                        li_value = delta['last_index'].replace('li-', '') if delta['last_index'] else '0'
                        lt_value = delta['log_last_term'].replace('lt-', '') if delta.get('log_last_term') else '0'
                        state_notes.append(f"Log: index={li_value}, term={lt_value}")
                    
                    if delta.get('commit_index'):
                        ci_value = delta['commit_index'].replace('ci-', '') if delta['commit_index'] else '0'
                        state_notes.append(f"Commit: index={ci_value}")
                    
                    if delta.get('term'):
                        t_value = delta['term'].replace('t-', '') if delta['term'] else '0'
                        state_notes.append(f"Term: {t_value}")
                    
                    # Add state change notes
                    for note in state_notes:
                        position = "left" if node_id == "1" else "right"
                        puml.append(f'note {position} of {node_alias}: {note}')

                # Update state history
                state_histories[node_index] = ns

        # Simplified legend - much smaller since messages are self-explanatory
        puml.extend([
            "",
            "legend right",
            '  <#GhostWhite,#GhostWhite>|      |= __Legend__ |',
            '  |<#Lightgreen>| Raft Node |',
            '  |FOLLOWER| Follower Role |',
            '  |CANDIDATE| Candidate Role |',
            '  |LEADER| Leader Role |',
            "endlegend",
            "@enduml"
        ])

        return puml

    def format_message_readable(self, message, node_state):
        """
        Format a message using readable formatters.
        
        Args:
            message: The message object
            node_state: The node state for context
            
        Returns:
            Readable string representation of the message
        """
        if isinstance(message, dict):
            message = decode_message(message)
        
        code = message.code
        formatter_class = READABLE_MESSAGE_FORMATTERS.get(code, ReadableMessageFormat)
        
        try:
            # Try to pass node_state for formatters that need it
            formatter = formatter_class(message, node_state)
        except TypeError:
            # Fallback for formatters that don't accept node_state
            formatter = formatter_class(message)
        
        return formatter.format()
