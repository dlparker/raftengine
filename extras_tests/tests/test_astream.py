import pytest

from rpc_common import RaftServerSim, seq_1, error_seq_1

async def test_astream_1():
    
    from raftengine.extras.astream_rpc import RPCServer, RPCClient
    await seq_1(RPCServer, RPCClient)
    await error_seq_1(RPCServer, RPCClient)
