import json
from raftengine.api.types import CommandResult
from raft_stubs.rpc_helper import RPCHelper
        
class RaftClient:

    def __init__(self, server_uri):
        self.current_leader_uri = server_uri
        self.rpc_client = None
        self.clients = {}
        self.rpc_helper = RPCHelper()
        
    def get_uri(self):
        return self.current_leader_uri

    async def connect(self, uri=None):
        if uri is None:
            uri = self.current_leader_uri
        tmp = uri.split('/')
        transport = tmp[0].split(':')[0]
        host, port = tmp[-1].split(':')
        self.rpc_client = await self.rpc_helper.rpc_client_maker(host, port)
        self.clients[uri] = self.rpc_client

    async def close(self):
        for uri,client in self.clients.items():
            await client.close()
        self.clients = {}
        self.rpc_client = None
        
    async def set_new_leader(self, uri):
        if uri not in self.clients:
            tmp = uri.split('/')
            transport = tmp[0].split(':')[0]
            host, port = tmp[-1].split(':')
            self.rpc_client = self.rpc_helper.rpc_client_maker(host, port)
            self.clients[uri] = self.rpc_client
            self.current_leader_uri = uri
            print("setting new leader %s", uri)
        return self.rpc_client
        
    async def run_command(self, command:str) -> CommandResult:
        if self.rpc_client is None:
            await self.connect()
        raw_result = await self.rpc_client.run_command(command)
        result = CommandResult(**json.loads(raw_result))
        if result.result:
            return result.result
        if result.error:
            raise Exception(f'got error from server {result.error}')
        if result.timeout_expired:
            raise Exception(f'got timeout at server, cluster not available')
        if result.redirect:
            await self.set_new_leader(result.redirect)
            return await self.run_command(command)
        if not result.retry:
            raise Exception(f"Command result does not make sense {result.__dict__}")
        start_time = time.time()
        while result.retry and time.time() - start_time < 1.0:
            await asyncio.sleep(0.0001)
            result = self.rpc_client.run_command(command)
        if result.retry:
            raise Exception('could not process message at server, cluster not available')
        
    async def raft_message(self, message:str) -> None:
        return await self.rpc_client.raft_message(message)
        
    

    
