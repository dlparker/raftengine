import asyncio
import time
import json
from raftengine.api.types import CommandResult
        
class RaftClient:

    def __init__(self, server_uri, rpc_client_class, timeout=10.0):
        self.leader_uri = server_uri
        self.rpc_client_class = rpc_client_class
        self.timeout = timeout
        self.rpc_client = None
        
    def get_uri(self):
        return self.leader_uri

    async def connect(self, uri=None):
        if uri is None:
            uri = self.leader_uri
        elif uri == self.leader_uri and self.rpc_client is not None:
            return
        if self.rpc_client is not None:
            c = self.rpc_client
            self.rpc_client = None
            asyncio.create_task(c.close())
        host, port = uri.split(':')[1:]
        port = int(port)
        host = host.lstrip('/')
        self.leader_uri = uri
        self.rpc_client = self.rpc_client_class(host, port, self.timeout * 2)

    async def close(self):
        if self.rpc_client is not None:
            await self.rpc_client.close()
        self.rpc_client = None
        
    async def issue_command(self, command:str, timeout=10.0, max_retries=50, retry_count=0) -> CommandResult:
        if self.rpc_client is None:
            await self.connect()
        raw_result = await self.rpc_client.issue_command(command, timeout=self.timeout)
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
            await self.connect(result.redirect)
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
        return await self.rpc_client.direct_server_command(command)
        
    

    
