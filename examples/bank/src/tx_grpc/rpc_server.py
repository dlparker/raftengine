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
    
    async def SendCommand(self, request, context):
        """Handle banking command requests"""
        result = await self.raft_server.run_command(request.command)
        return banking_pb2.CommandResponse(result=json.dumps(result.__dict__))
    
    async def RaftMessage(self, request, context):
        """Handle raft message requests"""
        result = await self.raft_server.raft_message(request.message)
        return banking_pb2.RaftResponse(result=result)
