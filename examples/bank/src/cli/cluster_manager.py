#!/usr/bin/env python
"""
Raft Cluster Manager using Textual - Interactive Terminal UI for managing a 3-node Raft cluster

This script provides a textual-based terminal interface for starting, stopping, and monitoring
a 3-node Raft banking cluster with real-time log aggregation and node status tracking.
"""


class NodeState(Enum):
    """Enumeration of possible node states"""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass
class NodeInfo:
    """Information about a Raft node"""
    index: int
    uri: str
    port: int
    state: NodeState
    process: Optional[asyncio.subprocess.Process] = None
    pid: Optional[int] = None
    start_time: Optional[datetime] = None
    log_lines: List[Tuple[datetime, str]] = None
    log_task: Optional[asyncio.Task] = None
    
    def __post_init__(self):
        if self.log_lines is None:
            self.log_lines = []


class ClusterManager(App):
    """
    Main cluster manager app using Textual for rich terminal UI
    """
    
    CSS = """
    Screen {
        layout: vertical;
    }
    
    .bordered {
        border: solid $primary;
    }
    
    .border-title {
        text-style: bold;
        color: $primary;
        height: 1;
        text-align: center;
    }
    
    #status_container {
        height: 14;
    }
    
    #logs_container {
        min-height: 10;
    }
    
    #command_container {
        height: 6;
    }
    
    DataTable {
        height: 100%;
    }
    
    RichLog {
        height: 100%;
    }
    
    Input {
        width: 100%;
    }
    """
    
    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", priority=True),
        Binding("f1", "show_help", "Help"),
        Binding("f2", "clear", "Clear"),
    ]
    def __init__(self, transport='grpc', base_port=50050):
        super().__init__()
        self.transport = transport
        self.base_port = base_port
        self.nodes = self._initialize_nodes()
        self.cluster_state = "stopped"
        self.log_buffer_size = 1000
        self.shutdown_event = asyncio.Event()
        self.update_interval = 0.5
        
        # Color schemes for each node
        self.node_colors = ["cyan", "green", "yellow"]
        
        # Initialize cluster control server_defs
        self._setup_server_defs()
        
    def _setup_server_defs(self):
        """Initialize server_defs for cluster control functions"""
        transport_offsets = {
            'astream': 0,
            'aiozmq': 100,
            'fastapi': 200,
            'grpc': 300
        }
        port_offset = transport_offsets[self.transport]
        
        # Import cluster control and initialize server_defs directly
        import cli.control_raft_server as cluster_control
        
        # Clear and initialize server definitions
        cluster_control.server_defs.clear()
        for index in range(3):
            port = self.base_port + port_offset + index
            url = f"{self.transport}://127.0.0.1:{port}"
            work_dir = Path('/tmp', f"raft_server.{self.transport}.{index}")
            
            cluster_control.server_defs[index] = {
                'url': url,
                'transport': self.transport,
                'work_dir': work_dir,
                'base_port': self.base_port + port_offset,
                'args_base_port': self.base_port,
                'port': port
            }
        
    def _initialize_nodes(self) -> Dict[int, NodeInfo]:
        """Initialize the 3-node cluster configuration"""
        nodes = {}
        # Calculate transport offset using the same pattern as control_raft_server.py
        transport_offsets = {
            'astream': 0,
            'aiozmq': 100,
            'fastapi': 200,
            'grpc': 300
        }
        port_offset = transport_offsets[self.transport]
        
        for i in range(3):
            port = self.base_port + port_offset + i
            uri = f"{self.transport}://127.0.0.1:{port}"
            nodes[i] = NodeInfo(
                index=i,
                uri=uri,
                port=port,
                state=NodeState.STOPPED
            )
        return nodes
    
    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()
        
        with Vertical():
            with Container(id="status_container", classes="bordered"):
                yield Static("Node Status", classes="border-title")
                yield DataTable(id="status_table")
                
            with Container(id="logs_container", classes="bordered"):
                yield Static("Aggregated Logs", classes="border-title")
                yield RichLog(id="logs_display", markup=True)
                
            with Container(id="command_container", classes="bordered"):
                yield Static("Commands", classes="border-title")
                yield Input(
                    placeholder="Commands: start, stop, restart, status, logs, clear, elect, start_raft, help, exit",
                    id="command_input"
                )
        
        yield Footer()
    
    def on_mount(self) -> None:
        """Called when app starts."""
        # Setup the status table with enhanced columns
        table = self.query_one("#status_table", DataTable)
        table.add_columns("Node", "URI", "State", "PID", "Role", "Term", "Leader")
        
        # Add initial rows for all nodes
        for node in self.nodes.values():
            table.add_row(
                f"Node {node.index}",
                node.uri,
                node.state.value,
                "-",
                "-",
                "-",
                "-"
            )
        
        # Start the status update timer
        self.set_interval(self.update_interval, self.update_status_display)
        
        # Start background log capture updates
        self.set_interval(0.1, self.update_logs_display)
        
        # Focus the command input
        self.query_one("#command_input", Input).focus()
    
    async def update_status_display(self) -> None:
        """Update the status table with current node information"""
        table = self.query_one("#status_table", DataTable)
        
        # Get RPCHelper for this transport
        nodes, RPCHelper = nodes_and_helper(self.transport, base_port=50050, node_count=3)
        
        # Clear and repopulate table
        table.clear()
        for node in self.nodes.values():
            # Use LocalCollector to get detailed status
            pid = "-"
            role = "-"
            term = "-"
            leader = "-"
            
            try:
                rpc_client = await RPCHelper().rpc_client_maker(node.uri)
                server_local_commands = LocalCollector(rpc_client)
                
                # Try to get PID first to see if server is reachable
                pid = await server_local_commands.get_pid()
                
                # If we got PID, server is running - get full status
                status = await server_local_commands.get_status()
                
                # Update node state based on actual status
                if node.state != NodeState.RUNNING:
                    node.state = NodeState.RUNNING
                    node.start_time = datetime.now()
                    # Start log monitoring for nodes that are now running
                    if not hasattr(node, 'log_task') or node.log_task is None:
                        node.log_task = asyncio.create_task(self._monitor_node_logs(node))
                
                node.pid = pid
                
                # Extract Raft status information
                if status.get('is_leader'):
                    role = f"[bold green]Leader[/bold green]"
                elif status.get('timers_running'):
                    role = f"[yellow]Follower[/yellow]"
                else:
                    role = f"[dim]Stopped[/dim]"
                
                term = str(status.get('term', '-'))
                leader_uri = status.get('leader_uri', '')
                if leader_uri:
                    # Extract just the port number for cleaner display
                    leader = leader_uri.split(':')[-1] if ':' in leader_uri else leader_uri
                else:
                    leader = "-"
                
                await rpc_client.close()
                
            except Exception:
                # Server not reachable or error occurred
                if node.state == NodeState.RUNNING:
                    node.state = NodeState.STOPPED
                    node.start_time = None
                    # Cancel log monitoring for stopped nodes
                    if hasattr(node, 'log_task') and node.log_task:
                        node.log_task.cancel()
                        node.log_task = None
                node.pid = None
            
            # Add row with current data
            table.add_row(
                f"Node {node.index}",
                node.uri,
                f"[{self._get_state_color(node.state)}]{node.state.value}[/]",
                str(pid) if pid != "-" else "-",
                role,
                term,
                leader
            )
    
    def _get_state_color(self, state: NodeState) -> str:
        """Get color for node state"""
        color_map = {
            NodeState.STOPPED: "red",
            NodeState.STARTING: "yellow",
            NodeState.RUNNING: "green",
            NodeState.STOPPING: "orange1",
            NodeState.ERROR: "red bold"
        }
        return color_map.get(state, "white")
    
    async def update_logs_display(self) -> None:
        """Update the logs display with recent log entries"""
        logs_widget = self.query_one("#logs_display", RichLog)
        
        # Get all log lines from all nodes with their total count for tracking
        total_log_count = 0
        for node in self.nodes.values():
            total_log_count += len(node.log_lines)
        
        # Initialize tracking if needed
        if not hasattr(self, '_last_total_log_count'):
            self._last_total_log_count = 0
        
        # Only update if we have new logs
        if total_log_count > self._last_total_log_count:
            # Get recent log lines from all nodes
            all_logs = []
            for node in self.nodes.values():
                for timestamp, line in node.log_lines:
                    all_logs.append((timestamp, node.index, line))
            
            # Sort by timestamp
            all_logs.sort(key=lambda x: x[0])
            
            # Show only new entries since last update
            new_entries = all_logs[self._last_total_log_count:]
            for timestamp, node_index, line in new_entries:
                time_str = timestamp.strftime("%H:%M:%S")
                color = self.node_colors[node_index]
                
                # Use Rich markup with RichLog
                log_line = f"[dim]{time_str}[/dim] [bold {color}]Node{node_index}[/bold {color}]: {line}"
                logs_widget.write(log_line)
            
            self._last_total_log_count = total_log_count
    
    @on(Input.Submitted, "#command_input")
    async def handle_command(self, event: Input.Submitted) -> None:
        """Handle command input submission"""
        command_line = event.value.strip()
        event.input.value = ""  # Clear the input
        
        if not command_line:
            return
        
        # Parse command and arguments
        parts = command_line.split()
        cmd = parts[0].lower()
        args = parts[1:]
        
        # Handle commands
        try:
            if cmd == 'exit':
                self.exit()
            elif cmd == 'start':
                result = await self.cmd_start(args)
                self._log_system(result)
            elif cmd == 'stop':
                result = await self.cmd_stop(args)
                self._log_system(result)
            elif cmd == 'restart':
                result = await self.cmd_restart(args)
                self._log_system(result)
            elif cmd == 'status':
                result = await self.cmd_status(args)
                self._log_system(result)
            elif cmd == 'logs':
                result = await self.cmd_logs(args)
                self._log_system(result)
            elif cmd == 'clear':
                result = await self.cmd_clear(args)
                self._log_system(result)
            elif cmd == 'elect':
                result = await self.cmd_elect(args)
                self._log_system(result)
            elif cmd == 'start_raft':
                result = await self.cmd_start_raft(args)
                self._log_system(result)
            elif cmd == 'help':
                result = await self.cmd_help(args)
                logs_widget = self.query_one("#logs_display", RichLog)
                logs_widget.write(result)
                #self._log_system(result)
            else:
                self._log_system(f"Unknown command: {cmd}. Type 'help' for available commands.")
                
        except Exception as e:
            self._log_system(f"Error: {e}")
    
    def _log_system(self, message: str) -> None:
        """Add a system message to the logs"""
        logs_widget = self.query_one("#logs_display", RichLog)
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Split multi-line messages and write each line separately
        lines = message.split('\n')
        for line in lines:
            if line.strip():
                # Use Rich markup with RichLog
                logs_widget.write(f"[dim]{timestamp}[/dim] [bold blue]SYSTEM[/bold blue]: {line}")
            else:
                logs_widget.write("")
    
    def _add_log_line(self, node_index: int, line: str):
        """Add a log line to a node's log buffer"""
        node = self.nodes[node_index]
        timestamp = datetime.now()
        node.log_lines.append((timestamp, line))
        
        # Trim log buffer
        if len(node.log_lines) > self.log_buffer_size:
            node.log_lines = node.log_lines[-self.log_buffer_size:]
    
    async def _start_node(self, node_index: int) -> bool:
        """Start a specific node using subprocess"""
        import subprocess
        import sys
        
        node = self.nodes[node_index]
        if node.state != NodeState.STOPPED:
            return False
        
        node.state = NodeState.STARTING
        self._add_log_line(node_index, f"Starting Node {node_index}...")
        
        try:
            # Use subprocess to start the server like cluster_control.py does
            raft_server_path = Path(Path(__file__).parent, 'raft_server.py')
            cmd = [sys.executable, str(raft_server_path), '--transport', self.transport,
                   '--index', str(node_index), '--slow_timeouts']
            
            work_dir = Path('/tmp', f"raft_server.{self.transport}.{node_index}")
            work_dir.mkdir(exist_ok=True)
            stdout_file = Path(work_dir, 'server.stdout')
            stderr_file = Path(work_dir, 'server.stderr')
            
            self._add_log_line(node_index, f"Command: {' '.join(cmd)}")
            
            with open(stdout_file, 'w') as stdout_f, open(stderr_file, 'w') as stderr_f:
                process = subprocess.Popen(cmd, stdout=stdout_f, stderr=stderr_f, start_new_session=True)
            
            # Wait a moment to see if process starts successfully
            await asyncio.sleep(0.5)
            if process.poll() is None:  # Process is still running
                node.state = NodeState.RUNNING
                node.start_time = datetime.now()
                node.process = process
                
                self._add_log_line(node_index, f"Node {node_index} started successfully")
                self._add_log_line(node_index, f"stdout: {stdout_file}")
                self._add_log_line(node_index, f"stderr: {stderr_file}")
                
                # Start log capture task for file-based monitoring
                node.log_task = asyncio.create_task(self._monitor_node_logs(node))
                
                return True
            else:
                node.state = NodeState.ERROR
                self._add_log_line(node_index, f"Node {node_index} failed to start")
                # Read the error logs
                if stderr_file.exists():
                    with open(stderr_file, 'r') as f:
                        stderr_content = f.read()
                    if stderr_content:
                        self._add_log_line(node_index, f"stderr: {stderr_content}")
                return False
                
        except Exception as e:
            node.state = NodeState.ERROR
            self._add_log_line(node_index, f"Failed to start: {e}")
            return False
    
    async def _stop_node(self, node_index: int) -> bool:
        """Stop a specific node using LocalCollector"""
        node = self.nodes[node_index]
        if node.state not in [NodeState.RUNNING, NodeState.STARTING]:
            return False
        
        node.state = NodeState.STOPPING
        self._add_log_line(node_index, f"Stopping Node {node_index}...")
        
        try:
            # Cancel the log capture task if it exists
            if hasattr(node, 'log_task') and node.log_task:
                node.log_task.cancel()
                try:
                    await node.log_task
                except asyncio.CancelledError:
                    pass
            
            # Use LocalCollector to send stop command
            nodes, RPCHelper = nodes_and_helper(self.transport, base_port=50050, node_count=3)
            try:
                rpc_client = await RPCHelper().rpc_client_maker(node.uri)
                server_local_commands = LocalCollector(rpc_client)
                await server_local_commands.stop_server()
                await rpc_client.close()
                
                node.state = NodeState.STOPPED
                node.process = None
                node.pid = None
                node.start_time = None
                if hasattr(node, 'log_task'):
                    node.log_task = None
                self._add_log_line(node_index, f"Node {node_index} stopped via RPC")
                return True
                
            except Exception as rpc_error:
                # If RPC fails, try direct process termination
                self._add_log_line(node_index, f"RPC stop failed, trying process termination: {rpc_error}")
                if hasattr(node, 'process') and node.process:
                    node.process.terminate()
                    await asyncio.sleep(1)
                    if node.process.poll() is None:
                        node.process.kill()
                    
                node.state = NodeState.STOPPED
                node.process = None
                node.pid = None
                node.start_time = None
                if hasattr(node, 'log_task'):
                    node.log_task = None
                self._add_log_line(node_index, f"Node {node_index} stopped via process termination")
                return True
                
        except Exception as e:
            self._add_log_line(node_index, f"Error stopping: {e}")
            node.state = NodeState.ERROR
            return False
    
    async def _monitor_node_logs(self, node: NodeInfo):
        """Monitor log files for a node"""
        work_dir = Path('/tmp', f"raft_server.{self.transport}.{node.index}")
        stdout_file = work_dir / 'server.stdout'
        stderr_file = work_dir / 'server.stderr'
        
        last_stdout_size = 0
        last_stderr_size = 0
        
        self._add_log_line(node.index, f"Starting log monitoring for Node {node.index}")
        
        try:
            # First, read existing log content if files exist
            if stdout_file.exists():
                try:
                    with open(stdout_file, 'r') as f:
                        existing_content = f.read()
                        for line in existing_content.splitlines():
                            if line.strip():
                                self._add_log_line(node.index, line)
                        last_stdout_size = len(existing_content.encode())
                except Exception as e:
                    self._add_log_line(node.index, f"Error reading existing stdout: {e}")
            
            if stderr_file.exists():
                try:
                    with open(stderr_file, 'r') as f:
                        existing_content = f.read()
                        for line in existing_content.splitlines():
                            if line.strip():
                                self._add_log_line(node.index, f"ERROR: {line}")
                        last_stderr_size = len(existing_content.encode())
                except Exception as e:
                    self._add_log_line(node.index, f"Error reading existing stderr: {e}")
            
            # Now monitor for new content
            while node.state == NodeState.RUNNING:
                try:
                    # Check stdout file
                    if stdout_file.exists():
                        current_size = stdout_file.stat().st_size
                        if current_size > last_stdout_size:
                            with open(stdout_file, 'r') as f:
                                f.seek(last_stdout_size)
                                new_content = f.read()
                                for line in new_content.splitlines():
                                    if line.strip():
                                        self._add_log_line(node.index, line)
                            last_stdout_size = current_size
                    
                    # Check stderr file
                    if stderr_file.exists():
                        current_size = stderr_file.stat().st_size
                        if current_size > last_stderr_size:
                            with open(stderr_file, 'r') as f:
                                f.seek(last_stderr_size)
                                new_content = f.read()
                                for line in new_content.splitlines():
                                    if line.strip():
                                        self._add_log_line(node.index, f"ERROR: {line}")
                            last_stderr_size = current_size
                    
                    await asyncio.sleep(0.1)  # Check every 100ms
                    
                except Exception as e:
                    self._add_log_line(node.index, f"Log monitoring error: {e}")
                    await asyncio.sleep(1)
                    
        except asyncio.CancelledError:
            self._add_log_line(node.index, f"Log monitoring cancelled for Node {node.index}")
            raise
        except Exception as e:
            self._add_log_line(node.index, f"Log monitoring error: {e}")
        
        self._add_log_line(node.index, f"Log monitoring ended for Node {node.index}")
    
    async def cmd_start(self, args: List[str]) -> str:
        """Start cluster or specific nodes"""
        if not args:
            # Start all nodes
            results = []
            for i in range(3):
                if await self._start_node(i):
                    results.append(f"✓ Node {i}")
                else:
                    results.append(f"✗ Node {i}")
            return "Start results: " + ", ".join(results)
        else:
            # Start specific nodes
            results = []
            for arg in args:
                try:
                    node_index = int(arg)
                    if 0 <= node_index <= 2:
                        if await self._start_node(node_index):
                            results.append(f"✓ Node {node_index}")
                        else:
                            results.append(f"✗ Node {node_index}")
                    else:
                        results.append(f"✗ Invalid node: {arg}")
                except ValueError:
                    results.append(f"✗ Invalid node: {arg}")
            return "Start results: " + ", ".join(results)
    
    async def cmd_stop(self, args: List[str]) -> str:
        """Stop cluster or specific nodes"""
        if not args:
            # Stop all nodes
            results = []
            for i in range(3):
                if await self._stop_node(i):
                    results.append(f"✓ Node {i}")
                else:
                    results.append(f"✗ Node {i}")
            return "Stop results: " + ", ".join(results)
        else:
            # Stop specific nodes
            results = []
            for arg in args:
                try:
                    node_index = int(arg)
                    if 0 <= node_index <= 2:
                        if await self._stop_node(node_index):
                            results.append(f"✓ Node {node_index}")
                        else:
                            results.append(f"✗ Node {node_index}")
                    else:
                        results.append(f"✗ Invalid node: {arg}")
                except ValueError:
                    results.append(f"✗ Invalid node: {arg}")
            return "Stop results: " + ", ".join(results)
    
    async def cmd_restart(self, args: List[str]) -> str:
        """Restart cluster or specific nodes"""
        if not args:
            # Restart all nodes
            await self.cmd_stop([])
            await asyncio.sleep(2)  # Brief pause
            return await self.cmd_start([])
        else:
            # Restart specific nodes
            stop_result = await self.cmd_stop(args)
            await asyncio.sleep(1)
            start_result = await self.cmd_start(args)
            return f"Restart: {stop_result} -> {start_result}"
    
    async def cmd_status(self, args: List[str]) -> str:
        """Show cluster status"""
        running = sum(1 for node in self.nodes.values() if node.state == NodeState.RUNNING)
        total = len(self.nodes)
        return f"Cluster status: {running}/{total} nodes running"
    
    async def cmd_logs(self, args: List[str]) -> str:
        """Show recent logs"""
        if not args:
            return "Recent logs are displayed in the main panel"
        
        try:
            node_index = int(args[0])
            if 0 <= node_index <= 2:
                node = self.nodes[node_index]
                recent_logs = node.log_lines[-10:]  # Last 10 lines
                if recent_logs:
                    log_text = f"Recent logs for Node {node_index}:"
                    for timestamp, line in recent_logs:
                        time_str = timestamp.strftime("%H:%M:%S")
                        log_text += f"\n[{time_str}] {line}"
                    return log_text
                else:
                    return f"No logs available for Node {node_index}"
            else:
                return f"Invalid node index: {node_index}"
        except (ValueError, IndexError):
            return "Usage: logs [node_index]"
    
    async def cmd_clear(self, args: List[str]) -> str:
        """Clear logs"""
        for node in self.nodes.values():
            node.log_lines.clear()
        
        # Clear the display logs too
        logs_widget = self.query_one("#logs_display", RichLog)
        logs_widget.clear()
        self._last_total_log_count = 0
        
        return "Logs cleared"
    
    async def cmd_elect(self, args: List[str]) -> str:
        """Trigger election on a specific node"""
        if not args:
            return "Usage: elect <node_index>"
        
        try:
            node_index = int(args[0])
            if 0 <= node_index <= 2:
                node = self.nodes[node_index]
                if node.state != NodeState.RUNNING:
                    return f"Node {node_index} is not running"
                
                # Use LocalCollector to trigger election
                nodes, RPCHelper = nodes_and_helper(self.transport, base_port=50050, node_count=3)
                try:
                    rpc_client = await RPCHelper().rpc_client_maker(node.uri)
                    server_local_commands = LocalCollector(rpc_client)
                    await server_local_commands.start_campaign()
                    await rpc_client.close()
                    
                    return f"Election triggered on Node {node_index}"
                except Exception as e:
                    return f"Failed to trigger election on Node {node_index}: {e}"
            else:
                return f"Invalid node index: {node_index}"
        except (ValueError, IndexError):
            return "Usage: elect <node_index>"
    
    async def cmd_start_raft(self, args: List[str]) -> str:
        """Start Raft operations on specific nodes"""
        if not args:
            # Start Raft on all running nodes
            results = []
            for i in range(3):
                node = self.nodes[i]
                if node.state == NodeState.RUNNING:
                    try:
                        nodes, RPCHelper = nodes_and_helper(self.transport, base_port=50050, node_count=3)
                        rpc_client = await RPCHelper().rpc_client_maker(node.uri)
                        server_local_commands = LocalCollector(rpc_client)
                        await server_local_commands.start_raft()
                        await rpc_client.close()
                        results.append(f"✓ Node {i}")
                    except Exception as e:
                        results.append(f"✗ Node {i}: {e}")
                else:
                    results.append(f"- Node {i} (not running)")
            return "Start Raft results: " + ", ".join(results)
        else:
            # Start Raft on specific nodes
            results = []
            for arg in args:
                try:
                    node_index = int(arg)
                    if 0 <= node_index <= 2:
                        node = self.nodes[node_index]
                        if node.state == NodeState.RUNNING:
                            try:
                                nodes, RPCHelper = nodes_and_helper(self.transport, base_port=50050, node_count=3)
                                rpc_client = await RPCHelper().rpc_client_maker(node.uri)
                                server_local_commands = LocalCollector(rpc_client)
                                await server_local_commands.start_raft()
                                await rpc_client.close()
                                results.append(f"✓ Node {node_index}")
                            except Exception as e:
                                results.append(f"✗ Node {node_index}: {e}")
                        else:
                            results.append(f"✗ Node {node_index} (not running)")
                    else:
                        results.append(f"✗ Invalid node: {arg}")
                except ValueError:
                    results.append(f"✗ Invalid node: {arg}")
            return "Start Raft results: " + ", ".join(results)
    
    async def cmd_help(self, args: List[str]) -> str:
        """Show help information"""
        help_text = f"""
Raft Cluster Manager - Transport: {self.transport}, Base Port: {self.base_port}

Available commands:
  start [node...]     - Start all nodes or specific nodes (0, 1, 2)
  stop [node...]      - Stop all nodes or specific nodes
  restart [node...]   - Restart all nodes or specific nodes
  start_raft [node...] - Start Raft operations on running nodes
  elect <node>        - Trigger election on specific node
  status              - Show cluster status summary
  logs [node]         - Show recent logs for all nodes or specific node
  clear               - Clear all log buffers
  help                - Show this help message
  exit                - Exit the cluster manager

Keyboard shortcuts:
  Ctrl+q              - Quit the application
  F1                  - Show this help
  F2                  - Clear log buffers

Examples:
  start               - Start all 3 nodes
  start 0 1           - Start nodes 0 and 1
  stop 2              - Stop node 2
  restart             - Restart all nodes
  start_raft          - Start Raft on all running nodes
  elect 1             - Make node 1 start an election
  logs 0              - Show recent logs for node 0

Status Table Columns:
  Node    - Node identifier
  URI     - Server endpoint
  State   - Server process state
  PID     - Process ID
  Role    - Raft role (Leader/Follower/Stopped)
  Term    - Current Raft term
  Leader  - Current leader port

Cluster Configuration:
  Transport: {self.transport}
  Base Port: {self.base_port}
  Working Directory Pattern: /tmp/raft_server.{self.transport}.<index>
"""
        return help_text
    
    def action_show_help(self) -> None:
        """Action to show help via F1 key"""
        async def _async_help():
            result = await self.cmd_help([])
            logs_widget = self.query_one("#logs_display", RichLog)
            logs_widget.write(result)
        
        asyncio.create_task(_async_help())
    
    def action_clear(self) -> None:
        """Action to clear logs via F2 key"""
        async def _async_clear():
            result = await self.cmd_clear([])
        
        asyncio.create_task(_async_clear())
    
    async def on_exit(self):
        pass

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Raft Cluster Manager (Textual)')
    parser.add_argument('--transport', '-t', 
                        choices=['astream', 'aiozmq', 'fastapi', 'grpc'],
                        default='grpc',
                        help='Transport mechanism to use (default: grpc)')
    parser.add_argument('--base-port', '-b', type=int, default=50050,
                        help='Base port for cluster (default: 50050)')
    parser.add_argument('--auto-start', action='store_true',
                       help='Automatically start all nodes on startup')
    
    args = parser.parse_args()
    
    app = ClusterManager(args.transport, args.base_port)
    app.run()


if __name__ == "__main__":
    import asyncio
    import argparse
    import sys
    import time
    from pathlib import Path
    from datetime import datetime
    from typing import Dict, List, Optional, Tuple
    from dataclasses import dataclass
    from enum import Enum
    from pathlib import Path
    from raftengine.deck.log_control import LogController
    # setup LogControl before importing any modules that might initialize it first
    LogController.controller = None
    log_control = LogController.make_controller()
    this_dir = Path(__file__).resolve().parent
    for parent in this_dir.parents:
        if parent.name == 'src':
            if parent not in sys.path:
                sys.path.insert(0, str(parent))
                break
    else:
        raise ImportError("Could not find 'src' directory in the path hierarchy")

    # Textual UI components
    from textual.app import App, ComposeResult
    from textual.containers import Container, Horizontal, Vertical
    from textual.widgets import Header, Footer, DataTable, Input, Static, RichLog
    from textual.reactive import reactive
    from textual.message import Message
    from textual.binding import Binding
    from textual import on

    # Rich components for markup
    from rich.text import Text

    # Add the banking demo directory to the path
    # Import control_server functions
    from cli.raft_admin_ops import TRANSPORT_CHOICES, nodes_and_helper, server_admin
    from raft_ops.local_ops import LocalCollector

    main()
