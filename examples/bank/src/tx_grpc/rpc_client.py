import asyncio
import grpc
from base.rpc_api import RPCAPI
from raftengine.api.deck_api import CommandResult

# Import generated gRPC code using absolute imports
from tx_grpc import banking_pb2, banking_pb2_grpc

class RPCClient(RPCAPI):
    
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.channel = None
        self.stub = None
        self.uri = f'grpc://{self.host}:{self.port}'

    def get_uri(self):
        return self.uri
    
    async def connect(self):
        """Establish connection to gRPC server"""
        address = f'{self.host}:{self.port}'
        self.channel = grpc.aio.insecure_channel(address)
        self.stub = banking_pb2_grpc.BankingServiceStub(self.channel)
    
    async def run_command(self, command:str) -> CommandResult:
        """Send a banking command to the server"""
        if self.stub is None:
            await self.connect()
        
        request = banking_pb2.CommandRequest(command=command)
        response = await self.stub.RunCommand(request)

        return CommandResult(
            command=response.command,
            error=response.error,
            redirect=response.redirect,
            retry=response.retry,
            result=response.result
        )
        
        return response.result
    
    async def raft_message(self, message:str) -> None:
        """Send a raft message to the server"""
        if self.stub is None:
            await self.connect()
        
        request = banking_pb2.RaftRequest(message=message)
        # we don't need response, it is always None, and we don't want to wait
        asyncio.create_task(self.stub.RaftMessage(request))
        return None
    
    async def close(self):
        """Close the client connection"""
        if self.channel is not None:
            await self.channel.close()
            self.channel = None
            self.stub = None
