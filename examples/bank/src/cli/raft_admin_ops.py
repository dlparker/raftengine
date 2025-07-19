import os
import time
import subprocess
from pathlib import Path
from raft_ops.local_ops import LocalCollector

TRANSPORT_CHOICES = ['astream', 'aiozmq', 'fastapi', 'grpc']

def nodes_and_helper(transport, base_port, node_count=3):
    # Validate combination
    if transport == "astream":
        from tx_astream.rpc_helper import RPCHelper
        base_port = base_port
    elif transport == "aiozmq":
        from tx_aiozmq.rpc_helper import RPCHelper
        base_port = base_port + 100
    elif transport == "fastapi":
        from tx_fastapi.rpc_helper import RPCHelper
        base_port = base_port + 200
    elif transport == "grpc":
        from tx_grpc.rpc_helper import RPCHelper
        base_port = base_port + 300
    else:
        raise Exception(f"invalid transport {transport}, try {valid_txs}")
    nodes = []
    for pnum in range(base_port, base_port + node_count):
        nodes.append(f"{transport}://127.0.0.1:{pnum}")

    return nodes, RPCHelper

async def stop_server(rpc_client, all_uris):
    uri = rpc_client.get_uri()
    print(all_uris)
    index = all_uris.index(uri)
    transport = uri.split(':')[0]
    work_dir = f"/tmp/raft_server.{transport}.{index}"
    
    server_local_commands = LocalCollector(rpc_client)
    try:
        pid = await server_local_commands.get_pid()
        # running and responding, command shutdown
        res = await server_local_commands.stop_server()
        print(f'Sent stop command to server {uri} {res}')
    except:
        pid_file = Path(work_dir, 'server.pid')
        if pid_file.exists():
            try:
                with open(pid_file) as f:
                    check_pid = int(f.read().strip())
                try:
                    # Send signal 0 to check if process exists
                    os.kill(check_pid, 0)
                except ProcessLookupError:
                    # Process doesn't exist, clean up stale PID file
                    pid_file.unlink()
            except (ValueError, IOError):
                # Invalid PID file, clean it up
                if pid_file.exists():
                    pid_file.unlink()
    if not pid:
        return
    start_time = time.time()
    gone = False
    try:
        # Send signal 0 to check if process exists
        os.kill(pid, 15)
    except ProcessLookupError:
        # Process doesn't exist, stop done
        print(f"server pid {pid} no longer running")
        gone = True
    while time.time() - start_time < 2.0 and not gone:
        try:
            # Send signal 0 to check if process exists
            os.kill(pid, 0)
        except ProcessLookupError:
            # Process doesn't exist, stop done
            print(f"server pid {pid} no longer running")
            gone = True
    if not gone:
        raise Exception(f'stopping {uri} failed')
    

async def tail_server_logs(rpc_client, all_uris, lines: int = 10):
    uri = rpc_client.get_uri()
    print(all_uris)
    index = all_uris.index(uri)
    transport = uri.split(':')[0]
    work_dir = f"/tmp/raft_server.{transport}.{index}"
    stdout_file = Path(work_dir,'server.stdout')
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

async def tail_server_errors(rpc_client, all_uris, lines: int = 10):
    uri = rpc_client.get_uri()
    print(all_uris)
    index = all_uris.index(uri)
    transport = uri.split(':')[0]
    work_dir = f"/tmp/raft_server.{transport}.{index}"
    stdout_file = Path(work_dir,'server.stderr')
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
