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

logger = logging.getLogger("test_code")


from raftengine.api.snapshot_api import SnapShot
from ops.cluster_mgr import ClusterMgr
from ops.command_loop import ClusterCLI
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
    logger.debug("\n"+outvalue)
    if outvalue.strip() == "":
        outvalue = None
    return outvalue
    
async def test_run_ops_json():

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
    assert len(cluster) == 3, f"Server {cluster['3'].uri} no exit"
    path = Path(new_config.working_dir)
    shutil.rmtree(path)

    logger.info(f"Stopping cluster {cluster_name}")
    stop_res_json = await run_command(cluster_name, working_parent=cluster_base_dir, find_local=True,
                                      run_ops=['stop_cluster'])
    logger.debug(stop_res_json)


async def test_cmd_ops():

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

    logger.info("Creating cluster")
    res = await run_command(cluster_name, working_parent=cluster_base_dir, create_local=True, run_ops=['cluster_status'],
                            json_output=False)
    for expected in ["index=0", "index=1", "index=2", "not running"]:
        assert expected in res

    mgr = ClusterMgr()
    find_res = await mgr.discover_cluster_files(search_dir=cluster_base_dir)
    mgr.selected = cluster_name
    start_cluster = await mgr.cluster_status()

    
    logger.info("Listing clusters")
    list_res = await run_command(cluster_name, working_parent=cluster_base_dir, find_local=True, run_ops=['list_clusters'],
                                  json_output=False)
    found = False
    for line in list_res.split('\n'):
        line=line.strip()
        if line.startswith(cluster_name):
            found  = True
            for index, spec in start_cluster.items():
                assert spec['config'].uri in line
    assert found

    # the above call does not call do_find_clusters as it pre-initializes the cluster manager, so we need to do it
    # directly
    cluster_cli = ClusterCLI(manager=ClusterMgr())
    # just make sure help doesn't crash
    with patch('sys.stdout', new=StringIO()) as fake_out:
        cluster_cli.do_help()
        res = fake_out.getvalue()
    logger.info("Direct call to find_clusters")
    with patch('sys.stdout', new=StringIO()) as fake_out:
        await cluster_cli.do_find_clusters()
        res = fake_out.getvalue()
    logger.debug(res)
    assert "No clusters" in res
    with patch('sys.stdout', new=StringIO()) as fake_out:
        await cluster_cli.do_find_clusters(search_dir=cluster_base_dir)
        res = fake_out.getvalue()
    logger.debug(res)
    assert cluster_name in res
    shutil.rmtree(cluster_base_dir)
    cluster_base_dir.mkdir()
    logger.info("Direct call to create_local_cluster")
    with patch('sys.stdout', new=StringIO()) as fake_out:
        await cluster_cli.do_create_local_cluster(cluster_name=cluster_name, directory=cluster_base_dir.parent, force=False)
        res = fake_out.getvalue()
    for index, spec in start_cluster.items():
        assert spec['config'].uri in res
    for line in res.split('\n'):
        line = line.strip()
        if line == '':
            continue
        assert line.startswith('index=')
    # now in case something changed, save this newer config
    start_cluster = await cluster_cli.manager.cluster_status()

        
    logger.info("Getting cluster status")
    res = await run_command(cluster_name, working_parent=cluster_base_dir, find_local=True, run_ops=['cluster_status'],
                                  json_output=False)
    for index, spec in start_cluster.items():
        assert spec['config'].uri in res
    
    logger.info("Checking some expected errors on non-running cluster")
    res = await run_command(cluster_name, working_parent=cluster_base_dir, find_local=True,
                          server_index='0', run_ops=['log_stats'], json_output=False)
    assert "Error"  in res
    assert "not running" in res
    res = await run_command(cluster_name, working_parent=cluster_base_dir, find_local=True,
                            run_ops=['send_heartbeats'], json_output=False)
    
    assert "Error"  in res
    assert "no servers are running" in res

    res = await run_command(cluster_name, working_parent=cluster_base_dir, find_local=True,
                            add_server="127.0.0.1:29999", run_ops=['new_server'], json_output=False)

    assert "Error"  in res
    assert "no servers are running" in res
    
    res = await run_command(cluster_name, working_parent=cluster_base_dir, find_local=True,
                            server_index='0', run_ops=['server_exit_cluster'], json_output=False)
    
    assert "Error"  in res
    assert "not running" in res

    logger.info("Starting servers")
    res = await run_command(cluster_name, working_parent=cluster_base_dir, find_local=True,
                            server_index='0', run_ops=['start_servers'], json_output=False)
    for index, spec in start_cluster.items():
        assert spec['config'].uri in res
    for line in res.split('\n'):
        line = line.strip()
        if line == '':
            continue
        assert line.startswith('index=')
    
    logger.info("Getting status")
    res = await run_command(cluster_name, working_parent=cluster_base_dir, find_local=True, run_ops=['cluster_status'],
                                  json_output=False)
    for index, spec in start_cluster.items():
        assert spec['config'].uri in res
    for line in res.split('\n'):
        line = line.strip()
        if line == '':
            continue
        assert line.startswith('index=')
        assert "running as" in line
        assert "not running" not in line

    logger.info("Waiting for leader")
    res = await run_command(cluster_name, working_parent=cluster_base_dir, find_local=True,
                                       run_ops=['server_status'], server_index=index, json_output=False)
        
    status = json.loads(res)
    start_time = time.time()
    while status['leader_uri'] is None and time.time() - start_time < 2:
        await asyncio.sleep(0.1)
        res = await run_command(cluster_name, working_parent=cluster_base_dir, find_local=True,
                                       run_ops=['server_status'], server_index=index, json_output=False)
        status = json.loads(res)
    assert status['leader_uri'] is not None

    logger.info("Ensuring do_add_cluster works")
    cluster_cli_2 = ClusterCLI(manager=ClusterMgr())
    with patch('sys.stdout', new=StringIO()) as fake_out:
        host, port = status['leader_uri'].split('/')[-1].split(':')
        await cluster_cli_2.do_add_cluster(port=port, host=host)
        res = fake_out.getvalue()
    logger.debug(res)
    with patch('sys.stdout', new=StringIO()) as fake_out:
        await cluster_cli_2.do_select(cluster_name)
        res = fake_out.getvalue()
    logger.debug(res)
    with patch('sys.stdout', new=StringIO()) as fake_out:
        await cluster_cli_2.do_cluster_status()
        res = fake_out.getvalue()
    for index, spec in start_cluster.items():
        assert spec['config'].uri in res
    for line in res.split('\n'):
        line = line.strip()
        if line == '':
            continue
        assert line.startswith('index=')
        assert "running as" in line
        assert "not running" not in line
    
    
    logger.info("Sending Heartbeats")
    res = await run_command(cluster_name, working_parent=cluster_base_dir, find_local=True,
                                       run_ops=['send_heartbeats'], json_output=False)
    assert "Heartbeats Sent" in res

    logger.info("Getting log stats")
    res = await run_command(cluster_name, working_parent=cluster_base_dir, find_local=True,
                                       run_ops=['log_stats'], server_index=index, json_output=False)
    stats = json.loads(res)
    assert stats['first_index'] is not None


    logger.info("Adding server to cluster")
    res = await run_command(cluster_name, working_parent=cluster_base_dir, find_local=True,
                            add_server='127.0.0.1',
                            run_ops=['new_server'], json_output=False)


    logger.info("Waiting for new server to show up")
    res = await run_command(cluster_name, working_parent=cluster_base_dir, find_local=True, run_ops=['cluster_status'],
                                  json_output=False)
    start_time = time.time()
    while "index=3" not in res and time.time() - start_time < 2:
        await asyncio.sleep(0.1)
        res = await run_command(cluster_name, working_parent=cluster_base_dir, find_local=True, run_ops=['cluster_status'],
                                  json_output=False)
    
    res = await run_command(cluster_name, working_parent=cluster_base_dir, find_local=True,
                            run_ops=['server_status'], server_index='3', json_output=False)
    status = json.loads(res)
    new_server_uri = status['uri']

    logger.info("Telling new server to take snapshot")
    res = await run_command(cluster_name, working_parent=cluster_base_dir, find_local=True,
                            run_ops=['take_snapshot'], server_index='3', json_output=False)
    assert "SnapShot(" in res
    
    logger.info("Stopping new server")
    res = await run_command(cluster_name, working_parent=cluster_base_dir, find_local=True,
                            run_ops=['stop_server'], server_index='3', json_output=False)

    for line in res.split('\n'):
        line = line.strip()
        if line.startswith("index=3"):
            assert "not running" in line
            
    logger.info("Restarting")
    res = await run_command(cluster_name, working_parent=cluster_base_dir, find_local=True,
                            run_ops=['start_servers'], json_output=False)

    logger.info("Telling new server to exit cluster")
    res = await run_command(cluster_name, working_parent=cluster_base_dir, find_local=True,
                            run_ops=['server_exit_cluster'], server_index='3', json_output=False)

    res = await run_command(cluster_name, working_parent=cluster_base_dir, find_local=True, run_ops=['cluster_status'],
                                  json_output=False)
    assert new_server_uri not in res
    
    logger.info("Stopping cluster")
    res = await run_command(cluster_name, working_parent=cluster_base_dir, find_local=True,
                            server_index='0', run_ops=['stop_cluster'], json_output=False)
    
    res = await run_command(cluster_name, working_parent=cluster_base_dir, find_local=True, run_ops=['cluster_status'],
                                  json_output=False)
    for index, spec in start_cluster.items():
        assert spec['config'].uri in res
    for line in res.split('\n'):
        line = line.strip()
        if line == '':
            continue
        assert line.startswith('index=')
        assert "running as" not in line
        assert "not running" in line

    return




async def test_cmd_ops_errors():
    logger.info("Direct call to find_clusters on")
    tdir = Path("/tmp/foo_bar_bee")
    if tdir.exists():
        shutil.rmtree(tdir)
    tdir.mkdir()
    
    cluster_cli = ClusterCLI(manager=ClusterMgr())

    with patch('sys.stdout', new=StringIO()) as fake_out:
        await cluster_cli.do_find_clusters(tdir)
        res = fake_out.getvalue()
    assert "No clusters found" in res
    assert str(tdir) in res

    with patch('sys.stdout', new=StringIO()) as fake_out:
        await cluster_cli.do_add_cluster(port=9999)
        res = fake_out.getvalue()
    assert "is it running" in res

    with patch('sys.stdout', new=StringIO()) as fake_out:
        await cluster_cli.do_list_clusters()
        res = fake_out.getvalue()
    assert "No clusters found" in res

    with patch('sys.stdout', new=StringIO()) as fake_out:
        await cluster_cli.do_cluster_status()
        res = fake_out.getvalue()
    assert "supply" in res

    with patch('sys.stdout', new=StringIO()) as fake_out:
        await cluster_cli.do_start_servers()
        res = fake_out.getvalue()
    assert "Error starting" in res

    with patch('sys.stdout', new=StringIO()) as fake_out:
        await cluster_cli.do_stop_cluster()
        res = fake_out.getvalue()
    assert "Error stopping" in res

    with patch('sys.stdout', new=StringIO()) as fake_out:
        await cluster_cli.do_server_status('0')
        res = fake_out.getvalue()
    assert "Error getting status" in res

    with patch('sys.stdout', new=StringIO()) as fake_out:
        await cluster_cli.do_log_stats('0')
        res = fake_out.getvalue()
    assert "Error getting log stats" in res
    
    with patch('sys.stdout', new=StringIO()) as fake_out:
        await cluster_cli.do_stop_server('0')
        res = fake_out.getvalue()
    assert "Error stopping server" in res
    
    with patch('sys.stdout', new=StringIO()) as fake_out:
        await cluster_cli.do_take_snapshot('0')
        res = fake_out.getvalue()
    assert "Error taking snapshot" in res
    
    with patch('sys.stdout', new=StringIO()) as fake_out:
        await cluster_cli.do_server_exit_cluster('0')
        res = fake_out.getvalue()
    assert "Error trying" in res
    assert "exit cluster" in res
    
    with patch('sys.stdout', new=StringIO()) as fake_out:
        await cluster_cli.do_send_heartbeats()
        res = fake_out.getvalue()
    assert "Error sending heartbeats" in res

    tdir = Path("/tmp/foo")
    if tdir.exists():
        shutil.rmtree(tdir)
    with patch('sys.stdout', new=StringIO()) as fake_out:
        await cluster_cli.do_create_local_cluster('foo', '/tmp/foo')
        res = fake_out.getvalue()
    assert "Error" not in res

    with patch('sys.stdout', new=StringIO()) as fake_out:
        await cluster_cli.do_create_local_cluster('foo', '/tmp/foo')
        res = fake_out.getvalue()
    assert "already exists" in res    
    if tdir.exists():
        shutil.rmtree(tdir)
