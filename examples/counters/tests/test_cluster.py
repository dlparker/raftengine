#!/usr/bin/env python
import os
import asyncio
import pytest
import logging
import json
import time
import shutil
import traceback
from io import StringIO
from pathlib import Path
from typing import Any
from pprint import pprint, pformat
from unittest.mock import patch
from raftengine.deck.log_control import LogController
from raftengine.api.log_api import LogStats

logger = logging.getLogger("test_code")

from raftengine.api.snapshot_api import SnapShot
from ops.cluster_mgr import ClusterMgr
from ops.command_loop import ClusterCLI
from ops.admin_common import ClusterServerConfig

async def run_server(working_dir):
    from ops.server_procs import main
    print(f"in run_server with {working_dir}")
    try:
        await main(Path(working_dir))
    except:
        traceback.print_exc()
        raise

async def add_and_run_server(working_dir, join_uri,  cluster_uri):
    from ops.server_procs import main
    print(f"in run_server with {working_dir} {join_uri} {cluster_uri}")
    try:
        await main(Path(working_dir), join_uri, cluster_uri)
    except:
        traceback.print_exc()
        raise

@pytest.mark.asyncio
async def test_one():
    mgr = ClusterMgr()
    cluster_name = "cluster_one"
    logger.setLevel('INFO')


    # We want to first start the servers with normal operations so that
    # we can do a restart on them to hit those code paths. Trying to restart
    # when they are running in process as task does not work, they can't get
    # their ports, so probably some kind of cleanup is missing on shutdown.
    # After a couple of hours trying to find it I decided to ignore the problem
    # as it causes no issues for actual server processes, just this funky test only
    # single process technique.
    logger.info(f"Creating cluster {cluster_name}")
    cluster_base_dir = Path("/tmp/test_clusters")
    if not cluster_base_dir.exists():
        cluster_base_dir.mkdir(parents=True)
    cr = await mgr.create_local_cluster(cluster_name, directory=cluster_base_dir, force=True)
    logger.debug("create_local_cluster result: %s", pformat(cr))

    logger.info(f"Starting servers normally")
    await mgr.start_servers()

    logger.info(f"Waiting for start")
    start_time = time.time()
    leader_uri = None
    leader_index = None
    pids = {}
    c_status = await mgr.cluster_status(cluster_name)
    for index,server in c_status.items():
        if server['status']:
            status = server['status']
            pids[index] = status['pid']
    start_time = time.time()
    while (len(pids) < 3 or leader_uri) is None and time.time() - start_time < 2:
        await asyncio.sleep(0.1)
        pids = {}
        c_status = await mgr.cluster_status(cluster_name)
        for index,server in c_status.items():
            if server['status']:
                status = server['status']
                pids[index] = status['pid']
    assert len(pids) == 3

    server_0 = c_status['0']
    logger.info("running validator to setup for reload of counters")
    from split_base.collector import Collector
    from base.validator import Validator
    from ops.admin_common import get_client
    client_0 = get_client(server_0['status']['uri'])
    collector = Collector(client_0)
    validator = Validator(collector)
    try:
        res = await validator.do_test()
    except:
        await mgr.stop_cluster()
        raise
    logger.info("trying some direct operations")
    res = await client_0.direct_server_command('getpid')
    logging_dict = await client_0.direct_server_command('get_logging_dict')
    old_value = logging_dict['loggers']['raft.RaftServer']['level']
    if old_value.upper == "INFO":
        new_value = "DEBUG"
    else:
        new_value = "INFO"
    await client_0.direct_server_command(f'set_logging_level raft.RaftServer {new_value}')
    logging_dict = await client_0.direct_server_command('get_logging_dict')
    assert logging_dict['loggers']['raft.RaftServer']['level'] == new_value
    await client_0.direct_server_command(f'set_logging_level raft.RaftServer {old_value}')
    
    res = await client_0.direct_server_command('dump_status')
    wdir = Path(server_0['config'].working_dir)
    stdout_file = Path(wdir, "server.stdout")
    with open(stdout_file, 'r') as f:
        buff = f.read()
    do_capture = False
    status_lines = []
    for line in buff.split('\n'):
        if "STATUS DUMP ENDS" in line:
            break
        if "STATUS DUMP BEGINS" in line:
            do_capture = True
        status_lines.append(line)
    data = '\n'.join(status_lines)
    assert "pid" in data
    logger.debug(f"Status from dump file\n{data}\n")
    assert len(status_lines) > 0

    
    logger.info(f"Stopping servers normally")
    await mgr.stop_cluster()
    logger.info(f"Waiting for stop")
    start_time = time.time()
    leader_uri = None
    leader_index = None
    pids = {}
    c_status = await mgr.cluster_status(cluster_name)
    for index,server in c_status.items():
        if server['status']:
            status = server['status']
            pids[index] = status['pid']
    start_time = time.time()
    while len(pids) > 0  and time.time() - start_time < 2:
        await asyncio.sleep(0.1)
        pids = {}
        c_status = await mgr.cluster_status(cluster_name)
        for index,server in c_status.items():
            if server['status']:
                status = server['status']
                pids[index] = status['pid']
    assert len(pids) == 0

    logger.info(f"Starting servers in tasks")
    start_servers = cr['servers_created']
    server_tasks = {}
    for index, server in start_servers.items():
        server_tasks[index] = asyncio.create_task(run_server(server['working_dir']))

    logger.info(f"Waiting for start")
    start_time = time.time()
    leader_uri = None
    leader_index = None
    pids = {}
    c_status = await mgr.cluster_status(cluster_name)
    for index,server in c_status.items():
        if server['status']:
            status = server['status']
            pids[index] = status['pid']
            if status['leader_uri'] is not None:
                leader_uri = status['leader_uri']
                leader_index = index
    start_time = time.time()
    while (len(pids) < 3 or leader_uri) is None and time.time() - start_time < 2:
        await asyncio.sleep(0.1)
        pids = {}
        c_status = await mgr.cluster_status(cluster_name)
        for index,server in c_status.items():
            if server['status']:
                status = server['status']
                pids[index] = status['pid']
                if status['leader_uri'] is not None:
                    leader_uri = status['leader_uri']
                    leader_index = index
    assert len(pids) == 3
    assert leader_uri is not None
    
    server_0 = c_status['0']
    logger.info("running validator")
    from split_base.collector import Collector
    from base.validator import Validator
    from ops.admin_common import get_client
    client_0 = get_client(server_0['status']['uri'])
    collector = Collector(client_0)
    validator = Validator(collector)
    try:
        res = await validator.do_test()
    except:
        await mgr.stop_cluster()
        raise

    
    logger.info("doing snapshot at server 0")
    log_stats_0_before = await mgr.log_stats(index='0')
    snap_rep = await mgr.take_snapshot(index='0')
    log_stats_0_after = await mgr.log_stats(index='0')
    snap = snap_rep['snapshot']
    assert log_stats_0_after.last_index >= snap.index
    assert log_stats_0_before.last_index <= snap.index

    leader_port = leader_uri.split(':')[-1]
    tmp = int(leader_port) // 10
    new_port = tmp * 10 + 3
    new_uri = f"sum://127.0.0.1:{new_port}"
    logger.info(f"adding new server at {new_uri}")
    server_tasks['3'] = asyncio.create_task(add_and_run_server(cluster_base_dir, new_uri, leader_uri))
    c_status = await mgr.cluster_status(cluster_name)
    start_time = time.time()
    while len(c_status) < 4 and time.time() - start_time < 1:
        await asyncio.sleep(0.1)
        c_status = await mgr.cluster_status(cluster_name)
    assert len(c_status) == 4
    server = c_status['3']
    config = server['config']


    logger.info(f"telling new server at {new_uri} to exit cluster")
    exit_res = await mgr.server_exit_cluster('3')
    start_time = time.time()
    while len(c_status) > 3 and time.time() - start_time < 1:
        await asyncio.sleep(0.1)
        c_status = await mgr.cluster_status(cluster_name)
    assert len(c_status) == 3

    logger.info("stopping cluster")
    await mgr.stop_cluster()
    for index, task in server_tasks.items():
        await task


    shutil.rmtree(cluster_base_dir)
    

    
    
        
