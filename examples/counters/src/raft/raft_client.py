import asyncio
import time
import json
from raftengine.api.types import CommandResult
from rpc.rpc_client import RPCClient
        
class RaftClient:

    def __init__(self, server_uri, timeout=10.0):
        self.server_uri = server_uri
        self.timeout = timeout
        self.rpc_client = None
        self.leader_uri = None
        self.leader_rpc_client = None
        
    def get_uri(self):
        return self.server_uri

    async def connect(self):
        if self.rpc_client is not None:
            return
        host, port = self.server_uri.split(':')[1:]
        port = int(port)
        host = host.lstrip('/')
        self.rpc_client = RPCClient(host, port, self.timeout * 2)

    async def connect_to_leader(self, uri):
        if self.leader_rpc_client is not None:
            if self.leader_uri == uri:
                return
            await self.leader_rpc_client.close()
        self.leader_uri = uri
        host, port = uri.split(':')[1:]
        port = int(port)
        host = host.lstrip('/')
        self.leader_rpc_client = RPCClient(host, port, self.timeout * 2)

    async def close(self):
        if self.rpc_client is not None:
            await self.rpc_client.close()
        self.rpc_client = None
        
    async def issue_command(self, command:str, timeout=10.0, max_retries=50, retry_count=0) -> CommandResult:
        if self.leader_rpc_client is not None:
            client = self.leader_rpc_client
        else:
            if self.rpc_client is None:
                await self.connect()
            client = self.rpc_client
        raw_result = await client.issue_command(command, timeout=self.timeout)
        try:
            result = CommandResult(**raw_result)
        except:
            raise Exception(f'cannot convert issue_command rpc result to CommandResult {raw_result}')
        if result.result:
            return result.result
        elif result.error:
            raise Exception(f'got error from server {result.error}')
        elif result.timeout_expired:
            raise Exception(f'got timeout at server, cluster not available')
        elif result.redirect:
            await self.connect_to_leader(result.redirect)
            return await self.issue_command(command, timeout)
        elif not result.retry:
            raise Exception(f"Command result does not make sense {result.__dict__}")

        # we got a retry, see if we can
        if retry_count < max_retries:
            retry_count += 1
            await asyncio.sleep(0.1)
            return await self.issue_command(command, max_retries=max_retries, retry_count=retry_count)
        else:
            raise Exception('could not process message at server, cluster not available, too many retries')
        
    async def raft_message(self, message:str) -> None:
        if self.rpc_client is None:
            await self.connect()
        return await self.rpc_client.raft_message(message)
        
    async def direct_server_command(self, command:str) -> None:
        if self.rpc_client is None:
            await self.connect()
        res = await self.rpc_client.direct_server_command(command)
        if isinstance(res, int):
            return res
        if "error" in res:
            raise Exception("Server error:\n" +  res['error'])
        return res
        
    

    
