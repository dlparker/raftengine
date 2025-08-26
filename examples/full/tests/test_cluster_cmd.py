#!/usr/bin/env python
import asyncio
import pytest
import logging
import json
import time
import shutil
import socket
from io import StringIO
from pathlib import Path
from typing import Any
from pprint import pprint, pformat
from unittest.mock import patch
from raftengine.deck.log_control import LogController
from raftengine.api.log_api import LogStats
from log_control import setup_logging

controller = setup_logging()
logger = logging.getLogger("test_code")

from raftengine.api.snapshot_api import SnapShot
from ops.cluster_mgr import ClusterMgr
from ops.admin_common import ClusterServerConfig

this_dir = Path(__file__).parent
root_dir = this_dir.parent
ops_dir = Path(root_dir, "src", "ops")
cmdr_path = Path(ops_dir, "cluster_cmd.py")


async def run_command(cluster_name, working_parent=None, find_local=False, create_local=False,
                      query_addr=None, server_index=None, add_server=None,
                      run_ops=None, json_output=True):

    if run_ops is None:
        msg = 'cannot run command loop here, must provide --run-ops value(s)'
        logger.error(msg)
        raise Exception(msg)
    if not find_local and not create_local and query_addr is None and working_parent is None:
        msg = "Must have a way to find or create a cluster"
        logger.error(msg)
        raise Exception(msg)
    if query_addr is None and working_parent is None:
        msg = "Must have a working_parent unless using query connect"
        logger.error(msg)
        raise Exception(msg)
    
    cmd = [str(cmdr_path), "--name", cluster_name]
    if json_output:
        cmd.append("-j")
    if working_parent is not None:
        cmd.append('-d')
        cmd.append(str(working_parent))
    if create_local:
        cmd.append('--create-local-cluster')
    if find_local:
        cmd.append('--local-cluster')
    if query_addr:
        cmd.append('--query-connect')
        cmd.append(query_addr)
    if server_index:
        cmd.append('--index')
        cmd.append(server_index)
    if add_server:
        cmd.append('--add-server')
        cmd.append(add_server)
    for op in run_ops:
        cmd.append('--run-ops')
        cmd.append(op)

    logger.debug(f"running cmd {cmd}")
    saved_log_controller = LogController.controller
    LogController.controller = None
    try:
        from ops.cluster_cmd import main 
        with patch('sys.stdout', new=StringIO()) as fake_out:
            with patch('sys.argv', cmd):
                await main()
                outvalue = fake_out.getvalue()
    finally:
        LogController.controller = saved_log_controller
        saved_log_controller.apply_config()
        
    logger.debug(outvalue)
    if outvalue.strip() == "":
        outvalue = None
    return outvalue
    
async def test_run_ops_full():

    setup_mgr = ClusterMgr()
    cluster_name = "test_run_ops"
    logger.info(f"Creating cluster {cluster_name}")
    cluster_base_dir = Path("/tmp", cluster_name)

    
    if cluster_base_dir.exists():
        try:
            await run_command(cluster_name, working_parent=cluster_base_dir, find_local=True, run_ops=['stop_cluster'])
        except:
            pass
        for sub in cluster_base_dir.glob('*'):
            if sub.is_dir():
                shutil.rmtree(sub)
            else:
                sub.unlink()
    else:
        cluster_base_dir.mkdir(parents=True)

    cr_str = await run_command(cluster_name, working_parent=cluster_base_dir, create_local=True, run_ops=['cluster_status'])

    from_files_mgr = ClusterMgr()
    # Now make sure that discover finds it
    # get the json version and make sure it doesn't blow up
    logger.info(f"Doing find_clusters and expecting to find {cluster_name}")
    cdict_str = await run_command(cluster_name, working_parent=cluster_base_dir, find_local=True, run_ops=['list_clusters'])
    #logger.debug("find_clusters result: %s", cdict_str)
    tmp = json.loads(cdict_str)
    # parse the JSON result from Task 1
    find_res = {'clusters': json.loads(cdict_str)}
    cdict = find_res['clusters']
    assert cluster_name in cdict
    servers = cdict[cluster_name]
    assert len(servers) == 3
    for item_dict in servers.values():
        item = ClusterServerConfig.from_dict(item_dict)
        assert isinstance(item, ClusterServerConfig)
    
    logger.info("Doing list_clusters to check jsonified result")
    l_str = await run_command(cluster_name, working_parent=cluster_base_dir, find_local=True, run_ops=['list_clusters'])
    c_data = json.loads(l_str)
    for cname,l_servers in c_data.items():
        f_servers = find_res['clusters'][cname]
        for index, l_spec in l_servers.items():
            f_spec_dict = f_servers[index]
            f_spec = ClusterServerConfig.from_dict(f_spec_dict)
            tmp = ClusterServerConfig.from_dict(l_spec)
            assert f_spec == tmp
            

    logger.info("Checking some expected errors on non-running cluster")
    # select_cluster not needed - cluster_name will be specified in each command line operation
    with pytest.raises(Exception) as excinfo:
        await run_command(cluster_name, working_parent=cluster_base_dir, find_local=True,
                          server_index='0', run_ops=['log_stats'])
    logger.debug(str(excinfo))
    assert "is not running" in str(excinfo) 
    with pytest.raises(Exception) as excinfo:
        await run_command(cluster_name, working_parent=cluster_base_dir, find_local=True,
                          run_ops=['send_heartbeats'])
    logger.debug(str(excinfo))
    assert "no servers are running" in str(excinfo) 
    with pytest.raises(Exception) as excinfo:
        await run_command(cluster_name, working_parent=cluster_base_dir, find_local=True,
                          add_server="127.0.0.1:29999", run_ops=['new_server'])
    logger.debug(str(excinfo))
    assert "no servers are running" in str(excinfo) 
    with pytest.raises(Exception) as excinfo:
        await run_command(cluster_name, working_parent=cluster_base_dir, find_local=True,
                          server_index='0', run_ops=['server_exit_cluster'])
    logger.debug(str(excinfo))
    assert "is not running" in str(excinfo) 
    c_str = await run_command(cluster_name, working_parent=cluster_base_dir, find_local=True, run_ops=['cluster_status'])
    l_servers = json.loads(c_str)
    saved_servers = {}
    for index, l_spec in l_servers.items():
        config = ClusterServerConfig.from_dict(l_spec['config'])
        saved_servers[index] = config
    find_port = saved_servers['0'].uri.split(':')[-1]
    
    with pytest.raises(Exception) as excinfo:
        await run_command(cluster_name, query_addr=f"127.0.0.1:{find_port}", run_ops=['cluster_status'])
    logger.debug(str(excinfo))
    assert "is it running" in str(excinfo)
    #assert "no servers are running" in str(excinfo) 
    
    logger.info(f"Starting servers in {cluster_name} (might be slow since it is first start of cluster)")
    start_res_json = await run_command(cluster_name, working_parent=cluster_base_dir, find_local=True,
                      run_ops=['start_servers'])

    logger.debug(f"Start servers result \n{start_res_json}")
    start_res = json.loads(start_res_json)
    for index, spec_dict in start_res['final_cluster_status'].items():
        config = ClusterServerConfig.from_dict(spec_dict['config'])
        assert spec_dict['status'] is not None


    logger.info("Ensuring add_cluster method works in non-json form")
    a_clust = await run_command(cluster_name, query_addr=f"127.0.0.1:{find_port}", run_ops=['cluster_status'])
    
    logger.info(f"Stopping cluster {cluster_name}")
    stop_res_json = await run_command(cluster_name, query_addr=f"127.0.0.1:{find_port}", run_ops=['stop_cluster'])
    logger.debug(stop_res_json)

    logger.info(f"Re-starting servers in {cluster_name} ")
    restart_res_json = await run_command(cluster_name, working_parent=cluster_base_dir, find_local=True,
                      run_ops=['start_servers'])
    logger.debug(pformat(restart_res_json))
    restart_res = json.loads(restart_res_json)
    saved_servers = {}
    for index, spec_dict in restart_res['final_cluster_status'].items():
        config = ClusterServerConfig.from_dict(spec_dict['config'])
        saved_servers[index] = config
        assert spec_dict['status'] is not None
        status_json = await run_command(cluster_name, working_parent=cluster_base_dir, find_local=True,
                                        run_ops=['server_status'], server_index=index)
        status = json.loads(status_json)
        assert status['pid'] == spec_dict['status']['pid']

    index = '1'
    log_stats_json = await run_command(cluster_name, working_parent=cluster_base_dir, find_local=True,
                                       run_ops=['log_stats'], server_index=index)
    
    log_stats = LogStats(**json.loads(log_stats_json))
    # takes a bit for election to happen
    start_time = time.time()
    while time.time() - start_time < 2 and log_stats.first_index is None:
        await asyncio.sleep(0.1)
        log_stats_json = await run_command(cluster_name, working_parent=cluster_base_dir, find_local=True,
                                       run_ops=['log_stats'], server_index=index)
        log_stats = LogStats(**json.loads(log_stats_json))
    
    assert log_stats.first_index is not None

    stop_res_j = await run_command(cluster_name, working_parent=cluster_base_dir, find_local=True,
                                        run_ops=['stop_server'], server_index=index)
    stop_res = json.loads(stop_res_j)
    assert stop_res['was_running']

    # wait for stop
    status_json = await run_command(cluster_name, working_parent=cluster_base_dir, find_local=True,
                                    run_ops=['server_status'], server_index=index)
    if status_json is None:
        status = None
    else:
        status = json.loads(status_json)
    start_time = time.time()
    while time.time() - start_time < 2 and status is not None:
        await asyncio.sleep(0.1)
        status_json = await run_command(cluster_name, working_parent=cluster_base_dir, find_local=True,
                                        run_ops=['server_status'], server_index=index)
        if status_json is None:
            status = None
        else:
            status = json.loads(status_json)
    assert status is None
    
    logger.info(f"starting servers in {cluster_name} should start currently stopped index {index}")
    restart_res_json = await run_command(cluster_name, working_parent=cluster_base_dir, find_local=True,
                      run_ops=['start_servers'])
    logger.debug(pformat(restart_res_json))
    restart_res = json.loads(restart_res_json)
    status_json = await run_command(cluster_name, working_parent=cluster_base_dir, find_local=True,
                                    run_ops=['server_status'], server_index=index)
    assert status_json is not None
    status = json.loads(status_json)
    
    # No way to check if this works, but lets make sure it doesn't blow up
    
    restart_res_json = await run_command(cluster_name, working_parent=cluster_base_dir, find_local=True,
                      run_ops=['send_heartbeats'])

    logger.info(f"Running validator to do some counter ops")
    # now put some stuff in the log
    from split_base.collector import Collector
    from base.validator import Validator
    from ops.admin_common import get_client
    client_0 = get_client(status['uri'])
    collector = Collector(client_0)
    validator = Validator(collector)
    try:
        res = await validator.do_test()
    except:
        stop_res_json = await run_command(cluster_name, working_parent=cluster_base_dir, find_local=True,
                                          run_ops=['stop_cluster'])
        raise

    for index in ['2', '1', '0']:
        logger.info(f"Taking snapshot on server {saved_servers[index].uri}")
        snap_json = await run_command(cluster_name, working_parent=cluster_base_dir, find_local=True,
                                        run_ops=['take_snapshot'], server_index=index)
        assert snap_json is not None
        
        snapshot_record = json.loads(snap_json)
        snapshot = SnapShot(**snapshot_record['snapshot'])
        log_stats_json = await run_command(cluster_name, working_parent=cluster_base_dir, find_local=True,
                                       run_ops=['log_stats'], server_index=index)
        log_stats = LogStats(**json.loads(log_stats_json))
        assert log_stats.snapshot_index == snapshot.index

    logger.info(f"Adding new server")
    add_res_json = await run_command(cluster_name, working_parent=cluster_base_dir, find_local=True,
                                     add_server='127.0.0.1',
                                     run_ops=['new_server'])
    add_res = json.loads(add_res_json)
    
    new_uri = add_res['uri']
    logger.info(f"Waiting for new server at {new_uri} to join cluster")
    a_clust = await run_command(cluster_name, working_parent=cluster_base_dir, find_local=True, run_ops=['cluster_status'])
    cluster = json.loads(a_clust)
    start_time = time.time()
    while time.time() - start_time < 2 and len(cluster) < 4:
        await asyncio.sleep(0.1)
        a_clust = await run_command(cluster_name, working_parent=cluster_base_dir, find_local=True, run_ops=['cluster_status'])
        cluster = json.loads(a_clust)
    assert len(cluster) == 4
    new_config = ClusterServerConfig.from_dict(cluster['3']['config'])
    logger.info(f"New server {new_uri} finished join, tell it to exist")
    exit_json = await run_command(cluster_name, working_parent=cluster_base_dir, find_local=True,
                                  run_ops=['server_exit_cluster'], server_index='3')
    exit_res = json.loads(exit_json)
    start_time = time.time()
    while time.time() - start_time < 2 and len(cluster) > 3:
        await asyncio.sleep(0.1)
        a_clust = await run_command(cluster_name, working_parent=cluster_base_dir, find_local=True, run_ops=['cluster_status'])
        cluster = json.loads(a_clust)
    assert len(cluster) == 3
    path = Path(new_config.working_dir)
    shutil.rmtree(path)

    logger.info(f"Stopping cluster {cluster_name}")
    stop_res_json = await run_command(cluster_name, working_parent=cluster_base_dir, find_local=True,
                                      run_ops=['stop_cluster'])
    logger.debug(stop_res_json)


