#!/usr/bin/env python

async def server_main(index, uri, cluster_config, local_config, RPCHelper, start_paused=True):
    work_dir = Path(local_config.working_dir)
    if not work_dir.exists():
        work_dir.mkdir(parents=True)
    with open(Path(work_dir, 'server.pid'), 'w') as f:
        f.write(f"{os.getpid()}")
    tmp = uri.split('/')
    host, port = tmp[-1].split(':')
    raft_server = RaftServer(cluster_config, local_config, RPCHelper)
    rpc_helper = RPCHelper(port)
    rpc_server = await rpc_helper.get_rpc_server(raft_server)
    raft_server.set_rpc_server_stopper(rpc_helper.stop_server_task)
    await rpc_helper.start_server_task()
    if not start_paused:
        await rpc_server.start()
        logger.info(f"{uri} server started")
    else:
        logger.info(f"{uri} RPC server started but awaiting start_raft RPC")
        
    while not raft_server.stopped:
        await asyncio.sleep(0.0001)
    

def update_cluster_config(log_db_file, initial_config):

    db = SqliteLog(log_db_file)
    config = db.get_cluster_config()
    for node_uri in initial_config.node_uris:
        if node_uri != config.nodes:
            config.nodes[node_uri] = NodeRec(uri=node_uri)
    for key in config.cluster_settings:
        config.cluster_settings = initial_config.key
    db.save_cluster_config(config)
    
async def main():

    parser = argparse.ArgumentParser(
        description='Teller Raft Server',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=args_epilog)

    tx_choices =  ["astream", "aiozmq", "fastapi", "grpc"]
    parser.add_argument(
        '-t', '--transport',
        required=True,
        choices=tx_choices,
        help='Transport mechanism within the step'
    )

    
    parser.add_argument('-b', '--base_port', type=int, default=50050,
                        help='Port number for first node in cluster')
    parser.add_argument('-i', '--index', type=int, required=True,
                        help='Index of this server node in cluster node list')
    parser.add_argument('-s', '--slow_timeouts', action='store_true',
                        help='Set raft timeout values to be extremely long')
    parser.add_argument('-w', '--startup_pause', action='store_true',
                        help='Wait for server.go file before starting raft server')
    parser.add_argument('--clear-data', action='store_true',
                        help='Clear Raft log and bank db, must be used with --tell-me-twice')
    parser.add_argument('--tell-me-twice', action='store_true',
                        help='Really do the dangerous thing requested')

    # Parse arguments
    args = parser.parse_args()
    if args.clear_data and not args.tell_me_twice:
        parser.error("--clear-data requires --tell-me-twice")

    # Get step and transport
    transport = args.transport
    
    # Validate combination
    if transport == "astream":
        from tx_astream.rpc_helper import RPCHelper
        base_port = args.base_port
    elif transport == "aiozmq":
        from tx_aiozmq.rpc_helper import RPCHelper
        base_port = args.base_port + 100
    elif transport == "fastapi":
        from tx_fastapi.rpc_helper import RPCHelper
        base_port = args.base_port + 200
    elif transport == "grpc":
        from tx_grpc.rpc_helper import RPCHelper
        base_port = args.base_port + 300
    else:
        raise Exception(f"invalid transport {transport}, try {valid_txs}")
    nodes = []
    for pnum in range(base_port, base_port + 3):
        nodes.append(f"{args.transport}://127.0.0.1:{pnum}")


    if args.slow_timeouts:
        heartbeat_period=10000
        election_timeout_min=20000
        election_timeout_max=20001
    else:
        heartbeat_period=0.01
        election_timeout_min=0.150
        election_timeout_max=0.350

    c_config = ClusterInitConfig(node_uris=nodes,
                                 heartbeat_period=heartbeat_period,
                                 election_timeout_min=election_timeout_min,
                                 election_timeout_max=election_timeout_max,
                                 use_pre_vote=False,
                                 use_check_quorum=True,
                                 max_entries_per_message=10,
                                 use_dynamic_config=False)

    work_dir = Path('/tmp', f"raft_server.{args.transport}.{args.index}")
    if args.clear_data:
        # already checked for --tell-me-twice above
        if work_dir.exists():
            shutil.rmtree(work_dir)
        work_dir.mkdir()
    elif not work_dir.exists():
        work_dir.mkdir()
    else:
        log_path = Path(work_dir, 'raflog.db')
        if log_path.exists():
            # Update the cluster settings to make sure the timeouts are set
            update_cluster_config(log_path, c_config)
        
    uri = nodes[args.index]
    local_config = LocalConfig(uri=uri, working_dir=work_dir)

    tmp = uri.split('/')
    host, port = tmp[-1].split(':')
    print(f"cluster nodes: {nodes}, starting {uri} with workdir={work_dir}")
    await server_main(args.index, uri, c_config,  local_config, RPCHelper)

args_epilog = """
Examples:
  %(prog)s --transport grpc --base_port 8080 --index 0
  %(prog)s  -t fastapi -b 8000 -i 1

Available transports:
  aiozmq, grpc, fastapi, astream
"""


if __name__ == "__main__":
    import asyncio
    import argparse
    import os
    import sys
    import shutil
    import logging
    from pathlib import Path
    from raftengine.api.types import NodeRec
    from raftengine.api.deck_config import ClusterInitConfig, LocalConfig

    from raftengine.deck.log_control import LogController
    # setup LogControl before importing any modules that might initialize it first
    LogController.controller = None
    log_control = LogController.make_controller()
    log_control.set_default_level("warning")
    logger = log_control.add_logger('server_main', 'The infrastructure elements of running a server processs')

    this_dir = Path(__file__).resolve().parent
    for parent in this_dir.parents:
        if parent.name == 'src':
            if parent not in sys.path:
                sys.path.insert(0, str(parent))
                break
    else:
        raise ImportError("Could not find 'src' directory in the path hierarchy")

    from raft_ops.raft_server import RaftServer
    from raft_ops.local_ops import LocalCollector
    from raft_ops.sqlite_log import SqliteLog

    #log_control.set_logger_level("Leader", "DEBUG")
    #log_control.set_logger_level("Follower", "DEBUG")
    #log_control.set_logger_level("Deck", "DEBUG")
    #log_control.set_logger_level("raft_ops.RaftServer", "DEBUG")
    asyncio.run(main())

