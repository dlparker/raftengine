#!/usr/bin/env python
"""
Raft Cluster Manager using Textual - Interactive Terminal UI for managing a 3-node Raft cluster

This script provides a textual-based terminal interface for starting, stopping, and monitoring
a 3-node Raft banking cluster with real-time log aggregation and node status tracking.
"""

import asyncio
import argparse
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

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
top_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(top_dir))

# Import control_server functions
from src.raft.raft_components.control_server import is_server_running, get_server_status, start_server, stop_server


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
    def __init__(self):
        super().__init__()
        self.nodes = self._initialize_nodes()
        self.cluster_state = "stopped"
        self.log_buffer_size = 1000
        self.shutdown_event = asyncio.Event()
        self.update_interval = 0.5
        
        # Color schemes for each node
        self.node_colors = ["cyan", "green", "yellow"]
        
    def _initialize_nodes(self) -> Dict[int, NodeInfo]:
        """Initialize the 3-node cluster configuration"""
        nodes = {}
        base_port = 50055
        for i in range(3):
            port = base_port + i
            uri = f"grpc://localhost:{port}"
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
                    placeholder="Type commands: start, stop, restart, status, logs, clear, help, exit",
                    id="command_input"
                )
        
        yield Footer()
    
    def on_mount(self) -> None:
        """Called when app starts."""
        # Setup the status table
        table = self.query_one("#status_table", DataTable)
        table.add_columns("Node", "URI", "State", "PID", "Uptime")
        
        # Add initial rows for all nodes
        for node in self.nodes.values():
            table.add_row(
                f"Node {node.index}",
                node.uri,
                node.state.value,
                "-",
                ""
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
        
        # Clear and repopulate table
        table.clear()
        for node in self.nodes.values():
            # Use control_server to get real status
            try:
                status = await get_server_status(node.index)
                
                # Update node state based on actual status
                if status['running']:
                    if node.state != NodeState.RUNNING:
                        node.state = NodeState.RUNNING
                        node.start_time = datetime.now()  # Approximate start time
                        # Start log monitoring for nodes that are already running
                        if not hasattr(node, 'log_task') or node.log_task is None:
                            node.log_task = asyncio.create_task(self._monitor_node_logs(node))
                    node.pid = status['pid']
                else:
                    if node.state == NodeState.RUNNING:
                        node.state = NodeState.STOPPED
                        node.start_time = None
                        # Cancel log monitoring for stopped nodes
                        if hasattr(node, 'log_task') and node.log_task:
                            node.log_task.cancel()
                            node.log_task = None
                    node.pid = None
                    
            except Exception:
                # If we can't get status, don't update the state
                pass
            
            # Calculate uptime
            uptime = ""
            if node.start_time and node.state == NodeState.RUNNING:
                delta = datetime.now() - node.start_time
                uptime = f"{delta.total_seconds():.0f}s"
            
            # Add row with current data
            table.add_row(
                f"Node {node.index}",
                node.uri,
                f"[{self._get_state_color(node.state)}]{node.state.value}[/]",
                str(node.pid) if node.pid else "-",
                uptime
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
        """Start a specific node using control_server"""
        node = self.nodes[node_index]
        if node.state != NodeState.STOPPED:
            return False
        
        node.state = NodeState.STARTING
        self._add_log_line(node_index, f"Starting Node {node_index}...")
        
        try:
            # Use control_server.start_server() instead of subprocess
            success = await start_server(node_index)
            if success:
                node.state = NodeState.RUNNING
                node.start_time = datetime.now()
                
                # Get PID from server status
                status = await get_server_status(node_index)
                node.pid = status.get('pid')
                
                self._add_log_line(node_index, f"Node {node_index} started successfully with PID {node.pid}")
                
                # Start log capture task for file-based monitoring
                node.log_task = asyncio.create_task(self._monitor_node_logs(node))
                
                return True
            else:
                node.state = NodeState.ERROR
                self._add_log_line(node_index, f"Failed to start Node {node_index}")
                return False
                
        except Exception as e:
            node.state = NodeState.ERROR
            self._add_log_line(node_index, f"Failed to start: {e}")
            return False
    
    async def _stop_node(self, node_index: int) -> bool:
        """Stop a specific node using control_server"""
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
            
            # Use control_server.stop_server() instead of direct process control
            success = await stop_server(node_index)
            if success:
                node.state = NodeState.STOPPED
                node.process = None
                node.pid = None
                node.start_time = None
                if hasattr(node, 'log_task'):
                    node.log_task = None
                self._add_log_line(node_index, f"Node {node_index} stopped")
                return True
            else:
                self._add_log_line(node_index, f"Failed to stop Node {node_index}")
                node.state = NodeState.ERROR
                return False
                
        except Exception as e:
            self._add_log_line(node_index, f"Error stopping: {e}")
            node.state = NodeState.ERROR
            return False
    
    async def _monitor_node_logs(self, node: NodeInfo):
        """Monitor log files for a node"""
        work_dir = Path('/tmp', f"rserver_{node.index}")
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
    
    async def cmd_help(self, args: List[str]) -> str:
        """Show help information"""
        help_text = """
Available commands:
  start [node...]     - Start all nodes or specific nodes (0, 1, 2)
  stop [node...]      - Stop all nodes or specific nodes
  restart [node...]   - Restart all nodes or specific nodes
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
  logs 0              - Show recent logs for node 0
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
    parser.add_argument('--auto-start', action='store_true',
                       help='Automatically start all nodes on startup')
    
    args = parser.parse_args()
    
    app = ClusterManager()
    app.run()


if __name__ == "__main__":
    main()
