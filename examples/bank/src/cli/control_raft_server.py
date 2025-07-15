#!/usr/bin/env python
import asyncio
import argparse
import sys
import subprocess
import traceback
import os
from pathlib import Path
this_dir = Path(__file__).resolve().parent
for parent in this_dir.parents:
    if parent.name == 'src':
        if parent not in sys.path:
            sys.path.insert(0, str(parent))
            src_dir = parent
            break
else:
    raise ImportError("Could not find 'src' directory in the path hierarchy")

# Note: Server control operations work directly with server_main.py 
# which handles its own src directory configuration

server_defs = {}

def is_server_running(index: int) -> bool:
    """Check if server is running using PID file"""
    server_spec = server_defs[index]
    work_dir = server_spec['work_dir']

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

def kill_server(index: int) -> bool:
    """Hard kill server if it is running"""
    server_spec = server_defs[index]
    work_dir = server_spec['work_dir']

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
            os.kill(pid, 9)
            pid_file.unlink()
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


async def get_server_status(index: int, nodes: list) -> dict:
    """Get detailed status of server"""
    server_spec = server_defs[index]
    work_dir = server_spec['work_dir']
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

async def start_server(index: int, pause=True, slow_timeouts=False) -> bool:
    server_spec = server_defs[index]
    """Start a server as a subprocess (async version)"""
    work_dir = server_spec['work_dir']
    if not work_dir.exists():
        work_dir.mkdir()

    pid_file = work_dir / 'server.pid'
    
    # Check if server is already running
    if is_server_running(index):
        print(f"Server {index} is already running")
        return False
    
    # Start the server process by calling server_main.py directly
    server_main_path = Path(Path(__file__).parent.parent, 'raft_ops' ,'server_main.py')
    cmd = [sys.executable, str(server_main_path), '--transport', server_spec['transport'],
           '--index', str(index), '--base_port', str(server_spec['args_base_port'])]
    if pause:
        cmd.append('--startup_pause')
    if slow_timeouts:
        cmd.append('--slow_timeouts')

    # Create log files for stdout and stderr
    stdout_file = work_dir / 'server.stdout'
    stderr_file = work_dir / 'server.stderr'
    
    try:
        # Set environment for unbuffered output and Python path
        env = os.environ.copy()
        env['PYTHONUNBUFFERED'] = '1'
        
        # Add src directory to PYTHONPATH
        current_path = env.get('PYTHONPATH', '')
        env['PYTHONPATH'] = str(src_dir)
        print(env['PYTHONPATH'])
        # Start process in background with log file redirection using subprocess.Popen
        # This ensures the process is truly detached from the parent
        print(" ".join(cmd))
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
        print(f"Error starting server {index}: {traceback.format_exc()}")
        return False

async def stop_server(index: int) -> bool:
    """Stop server using stop file (async version)"""
    server_spec = server_defs[index]
    work_dir = server_spec['work_dir']
    
    if not is_server_running(index):
        print(f"Server {index} is not running")
        return False
    
    stop_file = work_dir / 'server.stop'
    
    try:
        # Create stop file to trigger shutdown
        with open(stop_file, 'w') as f:
            f.write("stop")
        
        # Wait for server to stop
        max_wait = 2  # seconds
        for i in range(max_wait):
            if not is_server_running(index):
                print(f"Server {index} stopped successfully")
                return True
            await asyncio.sleep(1)  # Use async sleep
        
        print(f"Server {index} did not stop within {max_wait} seconds, killing")
        kill_server(index)
        
        return False
        
    except Exception as e:
        print(f"Error stopping server {index}: {e}")
        return False

async def tail_server_logs(index: int, lines: int = 10) -> bool:
    """Tail server stdout logs"""
    server_spec = server_defs[index]
    work_dir = server_spec['work_dir']
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
    server_spec = server_defs[index]
    work_dir = server_spec['work_dir']
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
    parser = argparse.ArgumentParser(
        description='Raft Banking Server Control',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  %(prog)s start --transport grpc --all
  %(prog)s stop --index 0
  %(prog)s status --transport fastapi --base_port 8000
  %(prog)s tail --index 1 --lines 50

Available transports:
  grpc, fastapi, aiozmq"""
    )
    
    parser.add_argument('command', choices=['start', 'stop', 'status', 'tail', 'tail_errors', 'go'],
                        help='Command to execute')
    parser.add_argument('--index', '-i', 
                        type=int, default=None,
                        help='Server index (0, 1, or 2)')
    parser.add_argument('--all', '-a', action='store_true',
                        help='Apply command to all servers')
    parser.add_argument('--lines', '-n', type=int, default=10,
                        help='Number of lines to show (for tail commands)')
    parser.add_argument('--startup_paused', '--pause', '-p', action='store_true',
                        help='Start servers paused, awaiting go file')
    parser.add_argument('--slow_timeouts', '-s', action='store_true',
                        help='Use slow timeouts for debugging (10+ seconds)')
    parser.add_argument('--transport', '-t', required=True,
                        choices=['astream', 'grpc', 'fastapi', 'aiozmq'],
                        help='Transport mechanism (default: grpc)')
    parser.add_argument('--base_port', '-b', type=int, default=50050,
                        help='Base port for first node (default: 50050)')
    
    args = parser.parse_args()
    
    # Build node list based on transport and base_port
    nodes = []
    transport = args.transport
    if transport == "astream":
        port_up = 0
    elif transport == "aiozmq":
        port_up = 100
    elif transport == "fastapi":
        port_up = 200
    elif transport == "grpc":
        port_up = 300
    else:
        raise Exception(f"invalid transport {transport}, try {valid_txs}")
    global server_defs
    for index,pnum in enumerate(range(args.base_port + port_up, args.base_port + port_up + 3)):
        url = f"{args.transport}://127.0.0.1:{pnum}"
        nodes.append(url)
        work_dir = Path('/tmp', f"raft_server.{args.transport}.{index}")
        server_defs[index] = dict(url=url, transport=args.transport, work_dir=work_dir,
                                  base_port=args.base_port + port_up,
                                  args_base_port=args.base_port, port=pnum)

    print(nodes)
    starting_all = False
    if args.all or args.index is None:
        indices = list(range(len(nodes)))
        starting_all = True
    else:
        indices = [args.index]
    
    if args.command == 'go':
        for index in indices:
            work_dir = server_defs[index]['work_dir']
            if work_dir.exists():
                with open(Path(work_dir, 'server.go'), 'w') as f:
                    f.write('')
        return
    
    if args.command == 'start':
        for index in indices:
            if starting_all and index == 0:
                # start 0 last so that it can hold an election and find
                # the others running
                continue
            await start_server(index, args.startup_paused, args.slow_timeouts)
        if starting_all:
            await start_server(0, args.startup_paused, args.slow_timeouts)
    
    elif args.command == 'stop':
        for index in indices:
            await stop_server(index)
    
    elif args.command == 'status':
        for index in indices:
            status = await get_server_status(index, nodes)
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
    
    
if __name__ == "__main__":
    asyncio.run(main())
