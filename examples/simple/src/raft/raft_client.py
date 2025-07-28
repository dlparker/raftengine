import asyncio
import time
import json
from raftengine.api.types import CommandResult
from rpc.rpc_client import RPCClient
        
class RaftClient:

    def __init__(self, server_uri):
        self.leader_uri = server_uri
        self.rpc_client = None
        
    def get_uri(self):
        return self.leader_uri

    async def connect(self, uri=None):
        if uri is None:
            uri = self.leader_uri
        elif uri == self.leader_uri and self.rpc_client is not None:
            return
        if self.rpc_client is not None:
            asyncio.create_task(self.rpc_client.stop())
        host, port = uri.split(':')[1:]
        port = int(port)
        host = host.lstrip('/')
        self.leader_uri = uri
        self.rpc_client = RPCClient(host, port)

    async def close(self):
        if self.rpc_client is not None:
            await self.rpc_client.close()
        self.rpc_client = None
        
    async def issue_command(self, command:str) -> CommandResult:
        if self.rpc_client is None:
            await self.connect()
        raw_result = await self.rpc_client.issue_command(command)
        result = CommandResult(**json.loads(raw_result))
        if result.result:
            return result.result
        elif result.error:
            raise Exception(f'got error from server {result.error}')
        elif result.timeout_expired:
            raise Exception(f'got timeout at server, cluster not available')
        elif result.redirect:
            await self.connect(result.redirect)
            return await self.issue_command(command)
        elif not result.retry:
            raise Exception(f"Command result does not make sense {result.__dict__}")
        start_time = time.time()
        while result.retry and time.time() - start_time < 1.0:
            await asyncio.sleep(0.0001)
            raw_result = await self.rpc_client.issue_command(command)
            result = CommandResult(**json.loads(raw_result))
        if result.retry:
            raise Exception('could not process message at server, cluster not available')
        
    async def raft_message(self, message:str) -> None:
        if self.rpc_client is None:
            await self.connect()
        return await self.rpc_client.raft_message(message)
        
    async def direct_server_command(self, command:str) -> None:
        if self.rpc_client is None:
            await self.connect()
        return await self.rpc_client.direct_server_command(command)
        
    

    
