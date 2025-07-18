import asyncio
import logging
import traceback
import json
import grpc
from concurrent import futures

# Import generated gRPC code using absolute imports
from tx_grpc import banking_pb2, banking_pb2_grpc

logger = logging.getLogger('bank.transport.server.grpc')

class RPCServer(banking_pb2_grpc.BankingServiceServicer):
    """gRPC servicer implementing the banking service interface"""
    
    def __init__(self, raft_server):
        self.raft_server = raft_server
    
    async def RunCommand(self, request, context):
        """Handle banking command requests"""
        try:
            logger.debug(f"Processing command via gRPC from {context.peer()}")
            result = await self.raft_server.run_command(request.command)
            return banking_pb2.CommandResult(
                command=result.command,
                error=result.error,
                redirect=result.redirect,
                retry=result.retry,
                result=result.result
            )
        except Exception as e:
            logger.error(f"Error processing command: {e}")
            logger.debug(traceback.format_exc())
            raise
    
    async def RaftMessage(self, request, context):
        """Handle raft message requests"""
        try:
            logger.debug(f"Processing raft message via gRPC from {context.peer()}")
            # we don't need response, it is always None, and we don't want to wait
            asyncio.create_task(self.raft_server.raft_message(request.message))
            return banking_pb2.RaftResponse(result=None)
        except Exception as e:
            logger.error(f"Error processing raft message: {e}")
            logger.debug(traceback.format_exc())
            raise

    async def LocalCommand(self, request, context):
        """Handle banking command requests"""
        try:
            logger.debug(f"Processing local command via gRPC from {context.peer()}")
            result = await self.raft_server.local_command(request.command)
            return banking_pb2.LocalResponse(result=result)
        except Exception as e:
            logger.error(f"Error processing local command: {e}")
            logger.debug(traceback.format_exc())
            raise
    
