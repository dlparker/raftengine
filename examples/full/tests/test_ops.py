#!/usr/bin/env python
import asyncio
import pytest
import logging
import json
import time
from typing import Any
from pprint import pprint, pformat
from log_control import setup_logging

controller = setup_logging()
logger = controller.add_logger("test_code")

import ops
from ops.cluster_mgr import ClusterMgr
from ops.admin_common import ClusterServerConfig

async def test_mgr_ops():
    mgr = ClusterMgr()

    cluster_name = "test_main_ops"
    logger.info(f"Creating cluster {cluster_name}")
    cr_str = await mgr.create_local_cluster(cluster_name, directory="/tmp", force=True, return_json=True)
    logger.debug("create_local_cluster result: %s", cr_str)
    create_result = json.loads(cr_str)
    assert create_result['success'] 
    assert create_result['cluster_name'] == cluster_name
    assert len(create_result['servers_created']) == 3

    # now make sure that discover finds it
    # get the json version and make sure it doesn't blow up
    logger.info(f"Doing find_clusters and expecting to find {cluster_name}")
    cdict_str = await mgr.find_clusters(return_json=True)
    #logger.debug("find_clusters result: %s", cdict_str)
    tmp = json.loads(cdict_str)
    # get the full objects version 
    find_res = await mgr.find_clusters()
    cdict = find_res['clusters']
    assert cluster_name in cdict
    servers = cdict[cluster_name]
    assert len(servers) == 3
    for item in servers.values():
        assert isinstance(item, ClusterServerConfig)
    
    logger.info("Doing list_clusters to check jsonified result")
    l_str = await mgr.list_clusters(return_json=True)
    c_data = json.loads(l_str)
    for cname,l_servers in c_data.items():
        f_servers = find_res['clusters'][cname]
        for index, l_spec in l_servers.items():
            f_spec = f_servers[index]
            tmp = ClusterServerConfig.from_dict(l_spec)
            assert f_spec == tmp

    await mgr.select_cluster(cluster_name)
    logger.info(f"Starting servers in {cluster_name} (might be slow since it is first start of cluster)")
    start_res_json = await mgr.start_servers(return_json=True)
    logger.info(f"Start servers result \n{start_res_json}")
    start_res = json.loads(start_res_json)
    for index, spec_dict in start_res['final_cluster_status'].items():
        config = ClusterServerConfig.from_dict(spec_dict['config'])
        assert spec_dict['status'] is not None
    
    logger.info(f"Stopping cluster {cluster_name}")
    stop_res_json = await mgr.stop_cluster(return_json=True)
    logger.debug(stop_res_json)

    logger.info(f"Re-starting servers in {cluster_name} ")
    restart_res = await mgr.start_servers(return_json=False)
    logger.debug(pformat(restart_res))
    for index, spec_dict in restart_res['final_cluster_status'].items():
        assert isinstance(config, ClusterServerConfig)
        assert spec_dict['status'] is not None
        status = await mgr.server_status(index)
        assert status['pid'] == spec_dict['status']['pid']
        status_json = await mgr.server_status(index, return_json=True)
        assert json.loads(status_json)['pid'] == spec_dict['status']['pid']

    c_status = await mgr.cluster_status(cluster_name)
    c_status_copy = await mgr.update_cluster(cluster_name)
    for index,o_server in c_status.items():
        copy_server = c_status_copy[index]
        o_config = o_server['config']
        copy_config = copy_server['config']
        assert o_config == copy_config
        o_status = o_server['status']
        copy_status = copy_server['status']
        for key in o_status:
            if key == "datetime":
                assert o_status[key] != copy_status[key]
            else:
                assert o_status[key] == copy_status[key]
                
    index = '1'
    start_time = time.time()
    log_stats = await mgr.log_stats(index)
    # takes a bit for election to happen
    while time.time() - start_time < 2 and log_stats.first_index is None:
        await asyncio.sleep(0.01)
        log_stats = await mgr.log_stats(index)

    assert log_stats.first_index is not None
    log_stats_j = await mgr.log_stats(index, return_json=True)
    log_stats_recon = json.loads(log_stats_j)
    assert log_stats_recon['first_index'] == log_stats.first_index
    
    stop_res_j = await mgr.stop_server(index, return_json=True)
    stop_res = json.loads(stop_res_j)
    assert stop_res['was_running']
    # wait for stop
    status = await mgr.server_status(index)
    start_time = time.time()
    while time.time() - start_time < 2 and status is not None:
        await asyncio.sleep(0.01)
        status = await mgr.server_status(index)
    assert status is None
    re_stop_res = await mgr.stop_server(index)
    assert not re_stop_res['was_running']

    start_res = await mgr.start_servers()
    status = await mgr.server_status(index)
    assert status is not None

    # No way to check if this works, but lets make sure it doesn't blow up
    res = await mgr.send_heartbeats()

    mgr2 = ClusterMgr()
    assert await mgr2.list_clusters() == {}
    assert await mgr2.list_clusters(return_json=True) == "{}"
    
    port = status['uri'].split(':')[-1]
    add_res = await mgr2.add_cluster(port)
    mgr2_status = await mgr2.server_status(index)

    for key in status:
        if key == "datetime":
            assert status[key] != mgr2_status[key]
        else:
            assert status[key] == mgr2_status[key]


    # now put some stuff in the log
    

            
    logger.info(f"Stopping cluster {cluster_name}")
    stop_res_json = await mgr.stop_cluster(return_json=True)
    logger.debug(stop_res_json)
