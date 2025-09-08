import os
import json
import asyncio
import pytest

class RaftServerSim:

    def __init__(self, rpc_server_class, rm_wait_for_result=False):
        self.rpc_server_class = rpc_server_class
        self.rm_wait_for_result = rm_wait_for_result
        self.rpc_server = None
        self.port = None
        
    async def start(self, port):
        self.port = port
        self.rpc_server = self.rpc_server_class(raft_server=self, rm_wait_for_result=self.rm_wait_for_result)
        await self.rpc_server.start(self.port)

    async def stop(self):
        if self.rpc_server:
            try:
                await self.rpc_server.stop()
            except asyncio.CancelledError as e:
                pass

    async def issue_command(self, command, timeout):
        if command == "raise":
            raise Exception('on command "raise"')
        if command == "delay":
            await asyncio.sleep(100.0)
        result = dict(result=command, error=None)
        return json.dumps(result)

    async def raft_message(self, message):
        if message == "raise":
            raise Exception('on message "raise"')
        return message

    async def direct_server_command(self, command):
        if command == "raise":
            raise Exception('on command "raise"')
        if command == "getpid":
            return os.getpid()
        else:
            return dict(error=f"unrecognized command {command}")

            
        
async def seq_1(rpc_server_class, rpc_client_class):
    server = RaftServerSim(rpc_server_class)
    port = 44444
    await server.start(port)
    client = rpc_client_class(host='127.0.0.1', port=port)

    assert "127.0.0.1" in client.get_uri()
    ic_res_j = await client.issue_command("a command", 1.0)
    assert ic_res_j is not None
    ic_res = json.loads(ic_res_j)
    assert ic_res['result'] == "a command"

    res = await client.raft_message("getpid")
    assert res is None

    pid_res = await client.direct_server_command("getpid")
    assert int(pid_res) == os.getpid()

    # The above sequence hits issue_command first, so the
    # check for connect in some implememtations failse
    # only in that method. We want it to happen in all, so
    # close, reopen and do other first
    await client.close()
    client = rpc_client_class(host='127.0.0.1', port=port)
    res = await client.raft_message("getpid")
    assert res is None

    await client.close()
    client = rpc_client_class(host='127.0.0.1', port=port)
    pid_res = await client.direct_server_command("getpid")
    assert int(pid_res) == os.getpid()

    await client.close()
    await server.stop()

    # do another test, but with wait for raft message flag True
    server = RaftServerSim(rpc_server_class, rm_wait_for_result=True)
    port = 44444
    await server.start(port)
    client = rpc_client_class(host='127.0.0.1', port=port)
    res = await client.raft_message("getpid")
    assert res is not None

    await client.close()
    await server.stop()

    
async def error_seq_1(rpc_server_class, rpc_client_class):
    server = RaftServerSim(rpc_server_class, rm_wait_for_result=True)
    port = 44444
    await server.start(port)
    client = rpc_client_class(host='127.0.0.1', port=port)

    with pytest.raises(Exception):
        await client.issue_command("raise", 1.0)

    with pytest.raises(Exception):
        await client.raft_message("raise")

    with pytest.raises(Exception):
        await client.direct_server_command("raise")

    await client.close()
    await server.stop()

