#!/usr/bin/env python
import asyncio
import argparse
import sys
import subprocess
import signal
import time
import os
from pathlib import Path
from operator import methodcaller
from raftengine.api.deck_config import ClusterInitConfig, LocalConfig
top_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(top_dir))
from src.raft.raft_components.server_main import server_main

nodes = ["grpc://localhost:50055",
         "grpc://localhost:50056",
         "grpc://localhost:50057",]

def old_start_server(index: int) -> bool:
    """Start a server as a subprocess"""
    work_dir = Path('/tmp', f"rserver_{index}")
    if not work_dir.exists():
        work_dir.mkdir()
    
    pid_file = work_dir / 'server.pid'
    
    # Check if server is already running
    if is_server_running(index):
        print(f"Server {index} is already running")
        return False
    
    # Start the server process by calling this script with 'run' command
    script_path = Path(__file__)
    cmd = [sys.executable, str(script_path), 'run', '--index', str(index)]
    
    # Create log files for stdout and stderr
    stdout_file = work_dir / 'server.stdout'
    stderr_file = work_dir / 'server.stderr'
    
    try:
        # Set environment for unbuffered output
        env = os.environ.copy()
        env['PYTHONUNBUFFERED'] = '1'
        
        # Start process in background with log file redirection
        with open(stdout_file, 'w') as stdout_f, open(stderr_file, 'w') as stderr_f:
            process = subprocess.Popen(cmd, 
                                     stdout=stdout_f, 
                                     stderr=stderr_f,
                                     env=env,
                                     start_new_session=True)
        
        # Wait a moment to see if process starts successfully
        time.sleep(0.5)
        
        if process.poll() is None:  # Process is still running
            print(f"Server {index} started successfully")
            print(f"  stdout: {stdout_file}")
            print(f"  stderr: {stderr_file}")
            return True
        else:
            print(f"Server {index} failed to start")
            # Read the error logs
            if stderr_file.exists():
                with open(stderr_file, 'r') as f:
                    stderr_content = f.read()
                if stderr_content:
                    print(f"stderr: {stderr_content}")
            return False
            
    except Exception as e:
        print(f"Error starting server {index}: {e}")
        return False

def is_server_running(index: int) -> bool:
    """Check if server is running using PID file"""
    work_dir = Path('/tmp', f"rserver_{index}")
    pid_file = work_dir / 'server.pid'
    
    if not pid_file.exists():
        return False
    
    try:
        with open(pid_file, 'r') as f:
            pid = int(f.read().strip())
        
        # Check if process with this PID exists
        try:
            # Send signal 0 to check if process exists
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            # Process doesn't exist, clean up stale PID file
            pid_file.unlink()
            return False
        except PermissionError:
            # Process exists but we don't have permission to signal it
            return True
            
    except (ValueError, IOError):
        # Invalid PID file, clean it up
        if pid_file.exists():
            pid_file.unlink()
        return False

def old_stop_server(index: int) -> bool:
    """Stop server using stop file"""
    work_dir = Path('/tmp', f"rserver_{index}")
    
    if not is_server_running(index):
        print(f"Server {index} is not running")
        return False
    
    stop_file = work_dir / 'server.stop'
    
    try:
        # Create stop file to trigger shutdown
        with open(stop_file, 'w') as f:
            f.write("stop")
        
        # Wait for server to stop
        max_wait = 10  # seconds
        for i in range(max_wait):
            if not is_server_running(index):
                print(f"Server {index} stopped successfully")
                return True
            time.sleep(1)
        
        print(f"Server {index} did not stop within {max_wait} seconds")
        return False
        
    except Exception as e:
        print(f"Error stopping server {index}: {e}")
        return False

async def get_server_status(index: int) -> dict:
    """Get detailed status of server"""
    work_dir = Path('/tmp', f"rserver_{index}")
    pid_file = work_dir / 'server.pid'
    
    status = {
        'index': index,
        'uri': nodes[index] if index < len(nodes) else 'unknown',
        'work_dir': str(work_dir),
        'running': is_server_running(index),
        'pid': None,
        'pid_file_exists': pid_file.exists()
    }
    
    if pid_file.exists():
        try:
            with open(pid_file, 'r') as f:
                status['pid'] = int(f.read().strip())
        except (ValueError, IOError):
            pass
    
    return status

async def start_server(index: int) -> bool:
    """Start a server as a subprocess (async version)"""
    work_dir = Path('/tmp', f"rserver_{index}")
    if not work_dir.exists():
        work_dir.mkdir()
    
    pid_file = work_dir / 'server.pid'
    
    # Check if server is already running
    if is_server_running(index):
        print(f"Server {index} is already running")
        return False
    
    # Start the server process by calling this script with 'run' command
    script_path = Path(__file__)
    cmd = [sys.executable, str(script_path), 'run', '--index', str(index)]
    
    # Create log files for stdout and stderr
    stdout_file = work_dir / 'server.stdout'
    stderr_file = work_dir / 'server.stderr'
    
    try:
        # Set environment for unbuffered output
        env = os.environ.copy()
        env['PYTHONUNBUFFERED'] = '1'
        
        # Start process in background with log file redirection using subprocess.Popen
        # This ensures the process is truly detached from the parent
        with open(stdout_file, 'w') as stdout_f, open(stderr_file, 'w') as stderr_f:
            process = subprocess.Popen(
                cmd,
                stdout=stdout_f,
                stderr=stderr_f,
                env=env,
                start_new_session=True
            )
        
        # Wait a moment to see if process starts successfully
        await asyncio.sleep(0.5)
        
        if process.poll() is None:  # Process is still running
            print(f"Server {index} started successfully")
            print(f"  stdout: {stdout_file}")
            print(f"  stderr: {stderr_file}")
            return True
        else:
            print(f"Server {index} failed to start")
            # Read the error logs
            if stderr_file.exists():
                with open(stderr_file, 'r') as f:
                    stderr_content = f.read()
                if stderr_content:
                    print(f"stderr: {stderr_content}")
            return False
            
    except Exception as e:
        print(f"Error starting server {index}: {e}")
        return False

async def stop_server(index: int) -> bool:
    """Stop server using stop file (async version)"""
    work_dir = Path('/tmp', f"rserver_{index}")
    
    if not is_server_running(index):
        print(f"Server {index} is not running")
        return False
    
    stop_file = work_dir / 'server.stop'
    
    try:
        # Create stop file to trigger shutdown
        with open(stop_file, 'w') as f:
            f.write("stop")
        
        # Wait for server to stop
        max_wait = 10  # seconds
        for i in range(max_wait):
            if not is_server_running(index):
                print(f"Server {index} stopped successfully")
                return True
            await asyncio.sleep(1)  # Use async sleep
        
        print(f"Server {index} did not stop within {max_wait} seconds")
        return False
        
    except Exception as e:
        print(f"Error stopping server {index}: {e}")
        return False

async def tail_server_logs(index: int, lines: int = 10) -> bool:
    """Tail server stdout logs"""
    work_dir = Path('/tmp', f"rserver_{index}")
    stdout_file = work_dir / 'server.stdout'
    
    if not stdout_file.exists():
        print(f"Server {index} stdout log file not found: {stdout_file}")
        return False
    
    try:
        cmd = ['tail']
        cmd.extend(['-n', str(lines), str(stdout_file)])
        
        # Run tail command
        subprocess.run(cmd)
        return True
        
    except KeyboardInterrupt:
        print("\nTail interrupted")
        return True
    except Exception as e:
        print(f"Error tailing server {index} logs: {e}")
        return False

async def tail_server_errors(index: int, lines: int = 10) -> bool:
    """Tail server stderr logs"""
    work_dir = Path('/tmp', f"rserver_{index}")
    stderr_file = work_dir / 'server.stderr'
    
    if not stderr_file.exists():
        print(f"Server {index} stderr log file not found: {stderr_file}")
        return False
    
    try:
        cmd = ['tail']
        cmd.extend(['-n', str(lines), str(stderr_file)])
        
        # Run tail command
        subprocess.run(cmd)
        return True
        
    except KeyboardInterrupt:
        print("\nTail interrupted")
        return True
    except Exception as e:
        print(f"Error tailing server {index} error logs: {e}")
        return False

async def main():
    parser = argparse.ArgumentParser(description='Raft Banking Server Control')
    parser.add_argument('command', choices=['start', 'stop', 'status', 'run', 'tail', 'tail_errors'],
                        help='Command to execute')
    parser.add_argument('--index', '-i', 
                        type=int, default=None,
                        help=f'Server index in list {nodes} (default: 0)')
    parser.add_argument('--all', '-a', action='store_true',
                        help='Apply command to all servers')
    parser.add_argument('--lines', '-n', type=int, default=10,
                        help='Number of lines to show (for tail commands)')
    args = parser.parse_args()
    
    if args.all or args.index is None:
        indices = list(range(len(nodes)))
    else:
        indices = [args.index]
    
    if args.command == 'start':
        for index in indices:
            await start_server(index)
    
    elif args.command == 'stop':
        for index in indices:
            await stop_server(index)
    
    elif args.command == 'status':
        for index in indices:
            status = await get_server_status(index)
            print(f"Server {index}: {status}")
    
    elif args.command == 'tail':
        if args.all:
            print("Cannot tail all servers simultaneously. Please specify --index.")
            return
        await tail_server_logs(indices[0], lines=args.lines)
    
    elif args.command == 'tail_errors':
        if args.all:
            print("Cannot tail all servers simultaneously. Please specify --index.")
            return
        await tail_server_errors(indices[0], lines=args.lines)
    
    elif args.command == 'run':
        # Run server directly (legacy mode)
        if len(indices) > 1:
            print("Cannot run multiple servers directly. Use 'start' command instead.")
            return
        
        index = indices[0]
        c_config = ClusterInitConfig(node_uris=nodes,
                                     heartbeat_period=10000,
                                     election_timeout_min=20000,
                                     election_timeout_max=20001,
                                     use_pre_vote=False,
                                     use_check_quorum=True,
                                     max_entries_per_message=10,
                                     use_dynamic_config=False)
        uri = nodes[index]
        work_dir = Path('/tmp', f"rserver_{index}")
        if not work_dir.exists():
            work_dir.mkdir()
        local_config = LocalConfig(uri=uri, working_dir=work_dir)
        await server_main(uri, c_config, local_config)
    
if __name__ == "__main__":
    asyncio.run(main())
