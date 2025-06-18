#!/usr/bin/env python
import asyncio
import logging
import pytest
import time
import json
from raftengine.hull.hull import Hull
from raftengine.messages.request_vote import RequestVoteMessage,RequestVoteResponseMessage
from raftengine.messages.pre_vote import PreVoteMessage,PreVoteResponseMessage
from raftengine.messages.append_entries import AppendEntriesMessage, AppendResponseMessage
from raftengine.messages.snapshot import SnapShotMessage, SnapShotResponseMessage
from raftengine.api.types import RoleName
from raftengine.api.log_api import LogRec
from dev_tools.pausing_cluster import PausingCluster, cluster_maker
from dev_tools.logging_ops import setup_logging

setup_logging()
logger = logging.getLogger("test_code")

async def test_bogus_pilot(cluster_maker):
    """
    Ensures that Hull constructor rejects Pilot class that does
    not implement PilotAPI
    """
    cluster = cluster_maker(3)
    cluster.test_trace.define_test("Testing Hull constructor with invalid Pilot", [], [])
    config = cluster.build_cluster_config()
    cluster.set_configs(config)
    uri_1 = cluster.node_uris[0]
    ts_1 = cluster.nodes[uri_1]
    class BadPilot:
        pass
    with pytest.raises(Exception):
        Hull(ts_1.cluster_init_config, ts_1.local_config, BadPilot())

async def test_str_methods():
    """
    Ensures that __str__ methods of internal classes don't blow
    up when called, and that the result contains at least something
    of the expected information. Not much of a test, but the
    doesn't-blow-up part is useful.
    """
    assert str(RoleName.leader) == 'LEADER'
    assert "request_vote" in str(RequestVoteMessage('a','b', 0, 0, 0))
    assert "request_vote_response" in str(RequestVoteResponseMessage('a','b', 0, 0, 0, True))
    assert "v=True" in str(RequestVoteResponseMessage('a','b', 0, 0, 0, True))
    assert "v=False" in str(RequestVoteResponseMessage('a','b', 0, 0, 0, False))
    assert "append_entries" in str(AppendEntriesMessage('a','b', 0, 0, 0, entries=[]))
    assert "append_response" in str(AppendResponseMessage('a','b', 0, 0, 0, 0, True, 'a'))
    assert "s=True" in str(AppendResponseMessage('a','b', 0, 0, 0, 0, True, 'a'))
    assert "s=False" in str(AppendResponseMessage('a','b', 0, 0, 0, 0, False, 'a'))

async def test_enum_edges():
    
    rec = LogRec(index=1, term=1, command="foo", committed=True, applied=True)
    assert str(rec.code) == "CLIENT_COMMAND"
    

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
    

    ssm = SnapShotMessage(sender='a', receiver='b', term=1, prevLogIndex=0, prevLogTerm=0,
                          leaderId="a", offset=0, done=True, data="[1,2]")
    assert "d=True" in str(ssm)

    ssmr = SnapShotResponseMessage(sender='b', receiver='a',term=1, prevLogIndex=0, prevLogTerm=0, offset=0, success=True)
    assert "s=True" in str(ssmr)
    assert ssmr.is_reply_to(ssm)
