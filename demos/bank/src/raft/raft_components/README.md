# Raft Cluster Manager

A sophisticated terminal-based cluster management interface for running and monitoring a 3-node Raft banking cluster built with Textual.

## Features

- **Textual Terminal UI**: Beautiful, responsive interface with split panels for status and logs
- **Process Management**: Start, stop, and restart individual nodes or the entire cluster
- **Real-time Log Aggregation**: Live log capture and display with Rich markup and node identification
- **Interactive Commands**: Full command set for cluster operations with command history and auto-completion
- **Color-coded Output**: Each node gets distinct colors (cyan, green, yellow) for easy identification
- **Keyboard Shortcuts**: Quick access to common functions (Ctrl+Q, F1, F2)
- **Graceful Shutdown**: Proper cleanup and process termination on exit

## Prerequisites

Install the required dependencies:

```bash
pip install -r requirements.txt
```

Make sure you have the raftengine package installed in editable mode:

```bash
# From the raftengine root directory
pip install -e .
```

## Usage

### Starting the Cluster Manager

```bash
python cluster_manager.py
```

Or make it executable and run directly:

```bash
chmod +x cluster_manager.py
./cluster_manager.py
```

### Available Commands

Type commands in the command input at the bottom of the screen:

- **`start`** - Start all 3 nodes
- **`start 0 1`** - Start specific nodes (0, 1, 2)
- **`stop`** - Stop all nodes
- **`stop 2`** - Stop specific node
- **`restart`** - Restart all nodes
- **`restart 1`** - Restart specific node
- **`status`** - Show cluster status summary
- **`logs`** - View aggregated logs (also shown in main panel)
- **`logs 0`** - Show recent logs for specific node
- **`clear`** - Clear all log buffers
- **`help`** - Show command help
- **`exit`** - Exit the cluster manager

### Keyboard Shortcuts

- **`Ctrl+Q`** - Quit the application
- **`F1`** - Show help information
- **`F2`** - Clear log buffers

### Example Session

```
┌─ Raft Cluster Manager ─────────────────────────────────────────┐
│ Interactive 3-Node Banking Cluster Control                     │
└─────────────────────────────────────────────────────────────────┘

# Type 'start' to start all nodes
start
[12:34:56] SYSTEM: Start results: ✓ Node 0, ✓ Node 1, ✓ Node 2

# Check status
status
[12:34:57] SYSTEM: Cluster status: 3/3 nodes running

# View logs from specific node
logs 0
[12:34:58] SYSTEM: Recent logs for Node 0:
[12:34:56] /tmp/rserver_50055.db
[12:34:56] grpc://localhost:50055 deck started

# Stop a specific node
stop 1
[12:34:59] SYSTEM: Stop results: ✓ Node 1
```

## UI Layout

The Textual interface is organized into four main sections:

1. **Header**: Application title and description
2. **Node Status Table**: Real-time table showing each node's:
   - URI (grpc://localhost:port)
   - State (stopped/starting/running/stopping/error)
   - Process ID (PID)
   - Uptime in seconds
3. **Aggregated Logs**: Scrollable log panel with:
   - Timestamped entries
   - Color-coded node identification
   - Rich markup for styling
   - System messages and node output
4. **Command Input**: Text input field with:
   - Command placeholder text
   - Auto-completion support
   - Command history

## Node Configuration

The cluster is pre-configured with 3 nodes:

- **Node 0**: `grpc://localhost:50055`
- **Node 1**: `grpc://localhost:50056`  
- **Node 2**: `grpc://localhost:50057`

Each node runs with its own SQLite database in `/tmp/rserver_[port].db`.

## Log Display

The log aggregation system provides:

- **Real-time capture** of stdout/stderr from each node process
- **Timestamp formatting** showing HH:MM:SS for each entry
- **Color-coded node names**: 
  - Node 0: Cyan
  - Node 1: Green 
  - Node 2: Yellow
- **Rich markup support** for styled text output
- **System messages** in blue for cluster manager operations
- **Automatic scrolling** to show latest entries

## Troubleshooting

### Common Issues

1. **Import Errors**: Make sure raftengine is installed and the path is correct
2. **Port Conflicts**: Ensure ports 50055-50057 are available
3. **Permission Errors**: Check that `/tmp/` is writable
4. **Dependencies**: Install all requirements from `requirements.txt`
5. **Textual Display Issues**: Ensure your terminal supports ANSI colors and Unicode

### Logs

All node output is captured and displayed in real-time in the logs panel. If a node fails to start, detailed error messages will appear with timestamps and node identification.

### Graceful Shutdown

Use the `exit` command or press `Ctrl+Q` to properly shutdown all running nodes and exit the manager. The application ensures all processes are terminated cleanly.

## Development

To extend the cluster manager:

1. **Add Commands**: Implement new async command methods in the `ClusterManager` class following the `cmd_*` pattern
2. **Modify UI**: Update the `compose()` method and CSS to change layout or styling
3. **Extend Monitoring**: Add more node metrics to the status table or create new display panels
4. **Configuration**: Make cluster configuration more flexible by modifying `_initialize_nodes()`
5. **Key Bindings**: Add new keyboard shortcuts by updating the `BINDINGS` list and adding corresponding `action_*` methods

## Files

- `cluster_manager.py` - Main Textual-based cluster management application
- `start_server.py` - Individual node startup script with proper stdout flushing
- `pilot.py` - Raft pilot implementation 
- `sqlite_log.py` - SQLite-based log storage
- `requirements.txt` - Python dependencies (includes textual>=0.41.0)
- `README.md` - This documentation

## Architecture

The cluster manager is built using modern Python async patterns:

- **Textual** for the terminal user interface and input handling
- **asyncio** for concurrent process management and log capture
- **Rich** for text styling and markup in log display
- **subprocess** for node process control with proper stdout/stderr capture
- **asyncio.create_task()** for background log monitoring

Key design features:

- **Async-first**: All operations use async/await for responsive UI
- **Task Management**: Proper lifecycle management of log capture tasks
- **Process Monitoring**: Real-time tracking of node process states
- **Error Handling**: Comprehensive error reporting with detailed diagnostics
- **Clean Separation**: UI logic separated from cluster management logic

Each node runs as an independent subprocess with dedicated log capture tasks that stream output to the aggregated display in real-time.