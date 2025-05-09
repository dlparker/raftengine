#!/usr/bin/env python
import asyncio
import logging
import time
import json
import random
from pathlib import Path
from pprint import pprint
import pytest
from raftengine.api.types import ClusterConfig, NodeRec, ClusterSettings
from raftengine.api.log_api import LogRec, RecordCode, LogAPI
from raftengine.api.pilot_api import PilotAPI
from raftengine.api.hull_config import ClusterInitConfig
from dev_tools.memory_log import MemoryLog
from dev_tools.sequences import SNormalElection, SNormalCommand, SPartialElection, SPartialCommand
from dev_tools.logging_ops import setup_logging
from dev_tools.pausing_cluster import PausingCluster, cluster_maker
from dev_tools.operations import DictTotalsOps, SnapShot

#extra_logging = [dict(name=__name__, level="debug"),]
#setup_logging(extra_logging)
default_level='error'
default_level='debug'
setup_logging(default_level=default_level)
logger = logging.getLogger("test_code")


# Stuff in here is just things that help me develop tests by writing
# explority code that runs in the test context, just to figure out
# what will work before adding it to real code.
# I might keep old code around for a while by renaming the test so
# it won't be gathered, then remove it when I am sure there is no
# more need for it.


async def test_message_ops():

    from raftengine.messages.log_msg import LogMessage
    from raftengine.messages.append_entries import AppendEntriesMessage, AppendResponseMessage
    from raftengine.messages.cluster_change import MembershipChangeMessage, MembershipChangeResponseMessage, ChangeOp
    from raftengine.messages.power import TransferPowerMessage, TransferPowerResponseMessage
    from raftengine.messages.pre_vote import PreVoteMessage, PreVoteResponseMessage
    from raftengine.messages.request_vote import RequestVoteMessage, RequestVoteResponseMessage
    
    rec_1 = LogRec(index=1, term=1, command="add 1", leader_id='mcpy://1', committed=True, applied=True)
    ae_1 = AppendEntriesMessage('mcpy://1', 'mcpy://2', term=1, prevLogIndex=0, prevLogTerm=0,
                               entries = [rec_1], commitIndex=0)
    re_1 = AppendResponseMessage('mcpy://2', 'mcpy://1', term=1, prevLogIndex=0, prevLogTerm=0, maxIndex=1, success=True, leaderId='mcpy://1')

    jd1 = json.dumps(ae_1, default=lambda o:o.__dict__)
    jd2 = json.dumps(re_1, default=lambda o:o.__dict__)
    c_ae_1 = AppendEntriesMessage.from_dict(json.loads(jd1))
    c_re_1 = AppendResponseMessage.from_dict(json.loads(jd2))
    assert c_re_1.is_reply_to(ae_1)
    assert re_1.is_reply_to(c_ae_1)
    assert str(ae_1) == str(c_ae_1)
    assert str(re_1) == str(c_re_1)

    mc_1 = MembershipChangeMessage('mcpy://1', 'mcpy://2', op=ChangeOp.add, target_uri="mcpy://4")
    rmc_1 = MembershipChangeResponseMessage('mcpy://2', 'mcpy://1', op=ChangeOp.add, target_uri="mcpy://4", ok=True)

    mc_jd1 = json.dumps(mc_1, default=lambda o:o.__dict__)
    rm_jd1 = json.dumps(rmc_1, default=lambda o:o.__dict__)
    c_mc_1 = MembershipChangeMessage.from_dict(json.loads(mc_jd1))
    c_rmc_1 = MembershipChangeResponseMessage.from_dict(json.loads(rm_jd1))
    assert str(mc_1) == str(c_mc_1)
    assert str(rmc_1) == str(c_rmc_1)
    assert c_rmc_1.is_reply_to(mc_1)


    tpm_1 = TransferPowerMessage('mcpy://1', 'mcpy://2', term=1, prevLogIndex=0, prevLogTerm=0)
    tpr_1 = TransferPowerResponseMessage('mcpy://2', 'mcpy://1', term=1, prevLogIndex=0, prevLogTerm=0, success=True)
    
    j_tpm_1 = json.dumps(tpm_1, default=lambda o:o.__dict__)
    j_tpr_1 = json.dumps(tpr_1, default=lambda o:o.__dict__)
    c_tpm_1 = TransferPowerMessage.from_dict(json.loads(j_tpm_1))
    c_tpr_1 = TransferPowerResponseMessage.from_dict(json.loads(j_tpr_1))
    assert c_tpr_1.is_reply_to(tpm_1)
    assert tpr_1.is_reply_to(c_tpm_1)
    assert str(tpm_1) == str(c_tpm_1)
    assert str(tpr_1) == str(c_tpr_1)

 
    pvm_1 = PreVoteMessage('mcpy://1', 'mcpy://2', term=1, prevLogIndex=0, prevLogTerm=0)
    pvr_1 = PreVoteResponseMessage('mcpy://2', 'mcpy://1', term=1, prevLogIndex=0, prevLogTerm=0, vote=True)
    
    j_pvm_1 = json.dumps(pvm_1, default=lambda o:o.__dict__)
    j_pvr_1 = json.dumps(pvr_1, default=lambda o:o.__dict__)
    c_pvm_1 = PreVoteMessage.from_dict(json.loads(j_pvm_1))
    c_pvr_1 = PreVoteResponseMessage.from_dict(json.loads(j_pvr_1))
    assert c_pvr_1.is_reply_to(pvm_1)
    assert pvr_1.is_reply_to(c_pvm_1)
    assert str(pvm_1) == str(c_pvm_1)
    assert str(pvr_1) == str(c_pvr_1)

    rvm_1 = RequestVoteMessage('mcpy://1', 'mcpy://2', term=1, prevLogIndex=0, prevLogTerm=0)
    rvr_1 = RequestVoteResponseMessage('mcpy://2', 'mcpy://1', term=1, prevLogIndex=0, prevLogTerm=0, vote=True)
    
    j_rvm_1 = json.dumps(rvm_1, default=lambda o:o.__dict__)
    j_rvr_1 = json.dumps(rvr_1, default=lambda o:o.__dict__)
    c_rvm_1 = RequestVoteMessage.from_dict(json.loads(j_rvm_1))
    c_rvr_1 = RequestVoteResponseMessage.from_dict(json.loads(j_rvr_1))
    assert c_rvr_1.is_reply_to(rvm_1)
    assert rvr_1.is_reply_to(c_rvm_1)
    assert str(rvm_1) == str(c_rvm_1)
    assert str(rvr_1) == str(c_rvr_1)
    

async def test_dict_ops():

    dto = DictTotalsOps(1)

    for i in range(1, 11):
        command = f'add {i} {random.randint(1,100)}'
        await dto.process_command(command, i)
    assert len(dto.totals) == 10
    ss = SnapShot(1,1)
    await dto.fill_snapshot(ss)
    assert len(ss.data) == 10

    ss2 = SnapShot(1,1)
    offset = 0
    done = False
    while not done:
        chunk, new_offset, done = await ss.get_chunk(offset)
        await ss2.save_chunk(chunk, offset)
        offset = new_offset
    dto_copy = DictTotalsOps(1)
    for line in ss2.data:
        await dto_copy.unpack_snapshot_data_item(line)

    for key in dto.totals:
        assert dto.totals[key] == dto_copy.totals[key]
    
async def test_snapshot_1(cluster_maker):

    cluster = cluster_maker(3)
    tconfig = cluster.build_cluster_config()
    cluster.set_configs(use_ops=DictTotalsOps)

    await cluster.start()
    uri_1, uri_2, uri_3 = cluster.node_uris
    ts_1, ts_2, ts_3 = [cluster.nodes[uri] for uri in [uri_1, uri_2, uri_3]]

    for i in range(10):
        for x in range(1, 10):
            command = f'add {x} {random.randint(1,100)}'
            for ts in [ts_1, ts_2, ts_3]:
                await ts.fake_command2(command)
                
    last_index,last_term = await ts_1.log.start_snapshot()
    rec = await ts_1.log.read(last_index)
    ts_1_ss = SnapShot(last_index, last_term)
    await ts_1.operations.fill_snapshot(ts_1_ss)
    await ts_1.log.install_snapshot(ts_1_ss)

    # log should now be empty
    assert await ts_1.log.read(last_index) is None
    assert await ts_1.log.get_first_index() is None
    assert await ts_1.log.read(last_index + 1) is None
    assert await ts_1.log.get_last_index() == ts_1_ss.get_last_index()
    assert await ts_1.log.get_last_term() == 1


    # Now start a snap shot but before finishing it add another record
    # This covers the idea that snapshots can happen concurrently with
    # new log records appending.
    tool_2 = ts_2.operations.get_snapshot_tool(ts_2.log)
    ts_2_ss = await tool_2.take_snapshot()
    await ts_2.fake_command2("add 1 1")
    assert ts_2.log.read(last_index + 2) is not None
    await ts_2.log.install_snapshot(ts_2_ss)
    assert await ts_2.log.read(last_index) is None
    final_rec_index = ts_2_ss.get_last_index() + 1
    assert await ts_2.log.get_first_index() == final_rec_index
    assert await ts_2.log.read(final_rec_index) is not None
    assert await ts_2.log.get_last_index() == final_rec_index
    assert await ts_2.log.get_last_term() == 1

    ts_4 = await cluster.add_node()
    tool_4  = ts_4.operations.get_snapshot_tool(ts_4.log)
    offset = 0
    done = False
    while not done:
        chunk, new_offset, done = await ts_2_ss.get_chunk(offset)
        if offset == 0:
            await tool_4.start_snapshot_load(ts_2_ss.get_last_index(), ts_2_ss.get_last_term(), chunk)
        else:
            await tool_4.continue_snapshot_load(chunk, offset, done)
        offset = new_offset

    # ts_2 has an additional record
    assert ts_4.operations.totals == ts_1.operations.totals
    assert await ts_4.log.get_first_index() == None
    assert await ts_4.log.get_last_index() == await ts_1.log.get_last_index()
    assert ts_4.operations.totals == ts_1.operations.totals
    assert await ts_4.log.get_last_index() != await ts_2.log.get_last_index()
    assert ts_4.operations.totals != ts_2.operations.totals
        
