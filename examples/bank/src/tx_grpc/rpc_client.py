import asyncio
import logging
import traceback
import grpc
from base.rpc_api import RPCAPI
from raftengine.api.deck_api import CommandResult

# Import generated gRPC code using absolute imports
from tx_grpc import banking_pb2, banking_pb2_grpc

logger = logging.getLogger('bank.transport.client.grpc')

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
        logger.debug(f"Establishing gRPC connection to {address}")
        self.channel = grpc.aio.insecure_channel(address)
        self.stub = banking_pb2_grpc.BankingServiceStub(self.channel)
        logger.info(f"Connected to gRPC server at {address}")
    
    async def run_command(self, command:str) -> CommandResult:
        """Send a banking command to the server"""
        if self.stub is None:
            await self.connect()
        
        try:
            request = banking_pb2.CommandRequest(command=command)
            response = await self.stub.RunCommand(request)

            return CommandResult(
                command=response.command,
                error=response.error,
                redirect=response.redirect,
                retry=response.retry,
                result=response.result
            )
        except Exception as e:
            logger.error(f"Error running command via gRPC: {e}")
            logger.debug(traceback.format_exc())
            raise
    
    async def raft_message(self, message:str) -> None:
        """Send a raft message to the server"""
        if self.stub is None:
            await self.connect()
        
        # We don't need the reply which is always none and waiting for it slows
        # down the Raft operations, so just spawn a task to do the message
        # delivery and return right away. The messages and the code
        # that uses them are designed to work with fully async message passing
        # mechanisms that do not reply to the message like an RPC does.
        async def send_raft_message():
            try:
                request = banking_pb2.RaftRequest(message=message)
                await self.stub.RaftMessage(request)
            except Exception as e:
                # Raft messages are fire-and-forget, so don't propagate errors
                logger.debug(f"Raft message send failed (expected): {e}")
        
        asyncio.create_task(send_raft_message())
        return None
    
    async def local_command(self, command:str) -> CommandResult:
        """Send a banking command to the server"""
        if self.stub is None:
            await self.connect()
        
        try:
            request = banking_pb2.LocalRequest(command=command)
            response = await self.stub.LocalCommand(request)
            return response.result
        except Exception as e:
            logger.error(f"Error running local command via gRPC: {e}")
            logger.debug(traceback.format_exc())
            raise
    
    async def close(self):
        """Close the client connection"""
        if self.channel is not None:
            logger.debug(f"Closing gRPC connection to {self.uri}")
            await self.channel.close()
            self.channel = None
            self.stub = None
            logger.debug(f"gRPC connection to {self.uri} closed")
