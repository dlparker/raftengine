import asyncio
import logging
import grpc
import json
import sys
from pathlib import Path
# Add the generated directory to the path
generated_path = Path(__file__).parent / 'generated'
sys.path.insert(0, str(generated_path))

import raft_service_pb2
import raft_service_pb2_grpc

logger = logging.getLogger('transport.client.grpc')


class RPCClient:
    
    def __init__(self, host, port, timeout=10.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.channel = None
        self.stub = None
        
    def get_uri(self):
        return f"grpc://{self.host}:{self.port}"

    async def connect(self):
        logger.debug(f"Creating gRPC channel to {self.host}:{self.port}")
        # Create async gRPC channel
        self.channel = grpc.aio.insecure_channel(f'{self.host}:{self.port}')
        self.stub = raft_service_pb2_grpc.RaftServiceStub(self.channel)
        logger.info(f"Connected to gRPC server at {self.host}:{self.port}")
    
    async def issue_command(self, command, timeout):
        """
        This is the client side method that will take the command and send
        it to the server side. When it gets there, it will make its way
        through whatever wiring exists until it reaches the Dispatcher's
        route_command method, and then the result of that method will be
        returned through all the wiring and the RPC pipe. This is
        required for Raft support.
        """
        if self.stub is None:
            await self.connect()
        
        request = raft_service_pb2.CommandRequest(command=command, raft_timeout=timeout)
        try:
            response = await self.stub.IssueCommand(request)
            # Deserialize the JSON response back to a dictionary
            return json.loads(response.result)
        except grpc.RpcError as e:
            logger.error(f"gRPC error in issue_command: {e}")
            raise Exception(f"gRPC error: {e}")

    async def raft_message(self, message):
        """
        This is the client side method of the RPC mechanism that Raftengine
        enabled servers use to sent Raft protocol messages. This call should
        never be used by the use client code. This is required for Raft support.
        """
        if self.stub is None:
            await self.connect()
        
        request = raft_service_pb2.MessageRequest(message=message)
        
        async def send_message():
            try:
                response = await self.stub.RaftMessage(request, timeout=self.timeout)
                return response.result
            except grpc.RpcError as e:
                # Raft messages are fire-and-forget, so don't propagate errors
                logger.debug(f"Raft message send failed (expected): {e}")
        
        # Fire-and-forget: spawn task and return immediately
        asyncio.create_task(send_message())
        return

    async def direct_server_command(self, command):
        """
        This is an optional RPC that allows user clients to perform operations
        on the server that answers the RPC interface. These operations will
        not be routed through Raftengine, so any effect that they have is
        strictly on the target server. Although optional, something like this
        is almost required for any reasonable level of monitoring and control
        of server processes.
        """
        if self.stub is None:
            await self.connect()
        
        request = raft_service_pb2.CommandRequest(command=command)
        try:
            response = await self.stub.DirectServerCommand(request, timeout=self.timeout)
            return json.loads(response.result)
        except grpc.RpcError as e:
            logger.error(f"gRPC error in direct_server_command: {e}")
            raise Exception(f"gRPC error: {e}")

    async def close(self):
        """Close the gRPC channel"""
        if self.channel is not None:
            logger.debug(f"Closing gRPC channel to {self.host}:{self.port}")
            await self.channel.close()
            self.channel = None
            self.stub = None
            logger.debug(f"gRPC channel to {self.host}:{self.port} closed")
            
    async def __aenter__(self):
        """Async context manager entry"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()
