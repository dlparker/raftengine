#!/usr/bin/env python
import asyncio
import pytest
import logging
import json
import time
import shutil
import socket
from pathlib import Path
from typing import Any
from pprint import pprint, pformat
from log_control import setup_logging

controller = setup_logging()
logger = controller.add_logger("test_code")

from raftengine.api.snapshot_api import SnapShot
from ops.cluster_mgr import ClusterMgr
from ops.admin_common import ClusterServerConfig

async def test_mgr_ops_full():

    setup_mgr = ClusterMgr()
    cluster_name = "test_main_ops"
    logger.info(f"Creating cluster {cluster_name}")
    cluster_base_dir = Path("/tmp/test_mgr_ops_clusters")
    if not cluster_base_dir.exists():
        cluster_base_dir.mkdir(parents=True)
    cr_str = await setup_mgr.create_local_cluster(cluster_name, directory=cluster_base_dir, force=True, return_json=True)
    logger.debug("create_local_cluster result: %s", cr_str)
    create_result = json.loads(cr_str)
    assert create_result['success'] 
    assert create_result['cluster_name'] == cluster_name
    assert len(create_result['servers_created']) == 3

    # make sure it blows up without force flag
    with pytest.raises(Exception):
         await setup_mgr.create_local_cluster(cluster_name, directory=cluster_base_dir, force=False)

    from_files_mgr = ClusterMgr()
    # Now make sure that discover finds it
    # get the json version and make sure it doesn't blow up
    logger.info(f"Doing discover_cluster_files and expecting to find {cluster_name}")
    cdict_str = await from_files_mgr.discover_cluster_files(search_dir=cluster_base_dir,return_json=True)
    #logger.debug("discover_cluster_files result: %s", cdict_str)
    tmp = json.loads(cdict_str)
    # get the full objects version 
    find_res = await from_files_mgr.discover_cluster_files(search_dir=cluster_base_dir)
    cdict = find_res['clusters']
    assert cluster_name in cdict
    servers = cdict[cluster_name]
    assert len(servers) == 3
    for item in servers.values():
        assert isinstance(item, ClusterServerConfig)
    
    logger.info("Doing list_clusters to check jsonified result")
    l_str = await from_files_mgr.list_clusters(return_json=True)
    c_data = json.loads(l_str)
    for cname,l_servers in c_data.items():
        f_servers = find_res['clusters'][cname]
        for index, l_spec in l_servers.items():
            f_spec = f_servers[index]
            tmp = ClusterServerConfig.from_dict(l_spec)
            assert f_spec == tmp
            

    logger.info("Checking some expected errors on non-running cluster")
    await from_files_mgr.select_cluster(cluster_name)
    with pytest.raises(Exception):
        await from_files_mgr.log_stats('0')
    with pytest.raises(Exception):
        await from_files_mgr.send_heartbeats()
    with pytest.raises(Exception):
        await from_files_mgr.new_server()
    with pytest.raises(Exception):
        await from_files_mgr.server_exit_cluster('0')
    with pytest.raises(Exception):
        await from_files_mgr.start_servers(hostnames=['foo', 'bar'])

    status_dict = await from_files_mgr.get_status()
    from_uri_mgr = ClusterMgr()
    find_port = servers['0'].uri.split(':')[-1]

    
    with pytest.raises(Exception):
        await from_uri_mgr.add_cluster(find_port)
    with pytest.raises(Exception):
        await from_uri_mgr.require_selection()
    with pytest.raises(Exception):
        await from_uri_mgr.cluster_status()
    with pytest.raises(Exception):
        await from_uri_mgr.update_cluster()
    
    logger.info(f"Starting servers in {cluster_name} (might be slow since it is first start of cluster)")
    start_res_json = await from_files_mgr.start_servers(return_json=True)
    logger.debug(f"Start servers result \n{start_res_json}")
    start_res = json.loads(start_res_json)
    for index, spec_dict in start_res['final_cluster_status'].items():
        config = ClusterServerConfig.from_dict(spec_dict['config'])
        assert spec_dict['status'] is not None


    logger.info("Ensuring add_cluster method works in non-json form")
    a_clust = await from_uri_mgr.add_cluster(find_port, return_json=False)
    logger.info("Testing some error conditions")
    orig = from_uri_mgr.selected
    from_uri_mgr.selected = None
    with pytest.raises(Exception):
        await from_uri_mgr.require_selection()
    with pytest.raises(Exception):
        await from_uri_mgr.get_status()
    with pytest.raises(Exception):
        await from_uri_mgr.select_cluster('foo')
    with pytest.raises(Exception):
        await from_uri_mgr.cluster_status()
    with pytest.raises(Exception):
        await from_uri_mgr.update_cluster()
    with pytest.raises(Exception):
        await from_uri_mgr.cluster_status('foo')
    with pytest.raises(Exception):
        await from_uri_mgr.update_cluster('foo')
    
    from_uri_mgr.selected = orig
    cluster, server, status =   from_uri_mgr.require_server_at_index('0')
    with pytest.raises(Exception):
        cluster, server, status = from_uri_mgr.require_server_at_index('4')
    
    assert a_clust['search_directory'] is None
    assert a_clust['query_uri'] is not None
    # start from scratch 
    from_uri_mgr = ClusterMgr()
    logger.info("Ensuring add_cluster method works in json form")
    b_clust_str = await from_uri_mgr.add_cluster(find_port, return_json=True)
    b_clust = json.loads(b_clust_str)
    assert b_clust['search_directory'] is None
    assert b_clust['query_uri'] is not None
    update_data = await from_uri_mgr.update_cluster()
    
    logger.info(f"Stopping cluster {cluster_name}")
    stop_res_json = await from_files_mgr.stop_cluster(return_json=True)
    logger.debug(stop_res_json)

    logger.info(f"Re-starting servers in {cluster_name} ")
    restart_res = await from_files_mgr.start_servers(return_json=False)
    logger.debug(pformat(restart_res))
    for index, spec_dict in restart_res['final_cluster_status'].items():
        assert isinstance(config, ClusterServerConfig)
        assert spec_dict['status'] is not None
        status = await from_files_mgr.server_status(index)
        assert status['pid'] == spec_dict['status']['pid']
        status_json = await from_files_mgr.server_status(index, return_json=True)
        assert json.loads(status_json)['pid'] == spec_dict['status']['pid']

    c_status = await from_files_mgr.cluster_status(cluster_name)
    c_status_copy = await from_files_mgr.update_cluster(cluster_name)
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
    log_stats = await from_files_mgr.log_stats(index)
    # takes a bit for election to happen
    while time.time() - start_time < 2 and log_stats.first_index is None:
        await asyncio.sleep(0.01)
        log_stats = await from_files_mgr.log_stats(index)

    assert log_stats.first_index is not None
    log_stats_j = await from_files_mgr.log_stats(index, return_json=True)
    log_stats_recon = json.loads(log_stats_j)
    assert log_stats_recon['first_index'] == log_stats.first_index
    
    stop_res_j = await from_files_mgr.stop_server(index, return_json=True)
    stop_res = json.loads(stop_res_j)
    assert stop_res['was_running']
    # wait for stop
    status = await from_files_mgr.server_status(index)
    start_time = time.time()
    while time.time() - start_time < 2 and status is not None:
        await asyncio.sleep(0.01)
        status = await from_files_mgr.server_status(index)
    assert status is None
    re_stop_res = await from_files_mgr.stop_server(index)
    assert not re_stop_res['was_running']

    start_res = await from_files_mgr.start_servers()
    status = await from_files_mgr.server_status(index)
    assert status is not None
    start_time = time.time()
    while time.time() - start_time < 2 and status['leader_uri'] is None:
        await asyncio.sleep(0.01)
        status = await from_files_mgr.server_status(index)
    assert status['leader_uri'] is not None

    # No way to check if this works, but lets make sure it doesn't blow up
    res = await from_files_mgr.send_heartbeats()

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
    from split_base.collector import Collector
    from base.validator import Validator
    from ops.admin_common import get_client
    client_0 = get_client(status['uri'])
    collector = Collector(client_0)
    validator = Validator(collector)
    try:
        res = await validator.do_test()
    except:
        stop_res_json = await from_files_mgr.stop_cluster(return_json=True)
        raise

    # use the json version to make sure it works, do server 0
    snapshot_record_j = await mgr2.take_snapshot('0', return_json=True)
    snapshot_record_0 = json.loads(snapshot_record_j)
    snapshot_0 = SnapShot(**snapshot_record_0['snapshot'])
    log_stats = await from_files_mgr.log_stats('0')
    assert log_stats.snapshot_index == snapshot_0.index
    
    # use the non json version to make sure it works, do server 1
    snapshot_record_1 = await mgr2.take_snapshot('1', return_json=False)
    snapshot_1 = snapshot_record_1['snapshot']
    log_stats_1 = await from_files_mgr.log_stats('1')
    assert log_stats_1.snapshot_index == snapshot_1.index

    # Now snapshot server 2, this will ensure tha new server gets a snapshot
    # on join
    snapshot_record_2 = await mgr2.take_snapshot('2', return_json=False)
    snapshot_2 = snapshot_record_2['snapshot']
    log_stats_2 = await from_files_mgr.log_stats('2')
    assert log_stats_2.snapshot_index == snapshot_2.index
    
    # now add a new server
    logger.info(f"Adding a new server to cluster")
    start_result = await from_files_mgr.new_server()
    c_status = await from_files_mgr.cluster_status()
    start_time = time.time()
    while len(c_status) < 4 and time.time() - start_time < 2:
        await asyncio.sleep(0.01)
        c_status = await from_files_mgr.cluster_status()
    assert len(c_status) == 4
    config = c_status['3']['config']
    logger.info(f"Added {config.uri} to cluster")

    # now remove that new server
    logger.info(f"Telling {config.uri} to exit cluster")
    exit_status = await from_files_mgr.server_exit_cluster('3')
    c_status = await from_files_mgr.cluster_status()
    start_time = time.time()
    while len(c_status) > 3 and time.time() - start_time < 2:
        await asyncio.sleep(0.01)
        c_status = await from_files_mgr.cluster_status()
    assert len(c_status) == 3
    path = Path(config.working_dir)
    shutil.rmtree(path)
    
    logger.info(f"Stopping cluster {cluster_name}")
    stop_res_json = await from_files_mgr.stop_cluster(return_json=True)
    logger.debug(stop_res_json)


async def test_cluster_create():

    mgr = ClusterMgr()
    cluster_name = "example_cluster"
    logger.info(f"Creating cluster {cluster_name}")
    cluster_base_dir = Path("/tmp", cluster_name)
    if not cluster_base_dir.exists():
        cluster_base_dir.mkdir(parents=True)
    else:
        for item in cluster_base_dir.glob('*'):
            shutil.rmtree(item)

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    host1 = socket.gethostname()
    s.connect(("8.8.8.8", 80))
    host2 = s.getsockname()[0]
    s.close()
    host3 = "otherhost"
    # put host 3 in the middle to mix up the index values on local servrs
    hosts = [host1, host3, host2]
    local_host_names = [host1, host2]
    cr_str = await mgr.create_cluster(cluster_name, local_servers_directory=cluster_base_dir,
                                            hosts=hosts, local_host_names=local_host_names, return_json=True)
    logger.debug("create_local_cluster result: %s", cr_str)
    create_result = json.loads(cr_str)
    assert create_result['cluster_name'] == cluster_name
    assert len(create_result['local_servers']) == 2

    local_configs = await mgr.get_local_server_configs(local_host_names)
    for index, config in local_configs.items():
        host = config.uri.split('/')[-1].split(':')[0]
        assert host in local_host_names
        assert index in ['0', '2']
        
    for index in range(3):
        config = await mgr.get_server_config(str(index))
        host = config.uri.split('/')[-1].split(':')[0]
        assert host in hosts

    # make sure we get an error on conflict
    with pytest.raises(Exception):
        create_result = await mgr.create_cluster(cluster_name, local_servers_directory=cluster_base_dir,
                                                 hosts=hosts, local_host_names=local_host_names)
    for item in cluster_base_dir.glob('*'):
        shutil.rmtree(item)
