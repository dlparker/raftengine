import asyncio
import json
import grpc
from concurrent import futures

# Import generated gRPC code using absolute imports
from tx_grpc import banking_pb2, banking_pb2_grpc

class RPCServer(banking_pb2_grpc.BankingServiceServicer):
    """gRPC servicer implementing the banking service interface"""
    
    def __init__(self, raft_server):
        self.raft_server = raft_server
    
    async def RunCommand(self, request, context):
        """Handle banking command requests"""
        result = await self.raft_server.run_command(request.command)
        return banking_pb2.CommandResult(
            command=result.command,
            error=result.error,
            redirect=result.redirect,
            retry=result.retry,
            result=result.result
        )


    
    async def RaftMessage(self, request, context):
        """Handle raft message requests"""
        # we don't need response, it is always None, and we don't want to wait
        asyncio.create_task(self.raft_server.raft_message(request.message))
        result = None
        return banking_pb2.RaftResponse(result=result)
