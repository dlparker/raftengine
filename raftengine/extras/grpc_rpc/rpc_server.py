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



class RaftServicer(raft_service_pb2_grpc.RaftServiceServicer):
    """gRPC servicer implementation"""
    
    def __init__(self, raft_server, rm_wait_for_result=False):
        self.raft_server = raft_server
        self.rm_wait_for_result = rm_wait_for_result
        # the logger is done this way to aid in testing, allowing check for caught errors
        self.logger = logging.getLogger('transport.server.grpc')

    async def IssueCommand(self, request, context):
        """Handle issue_command requests"""
        try:
            self.logger.debug(f"Processing command via gRPC: {request.command[:50]}...")
            result = await self.raft_server.issue_command(request.command, request.raft_timeout)
            # Handle CommandResult objects properly
            json_result = json.dumps(result, default=lambda o: o.__dict__)
            return raft_service_pb2.CommandResponse(result=json_result)
        except Exception as e:
            self.logger.error(f"Error processing command: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return raft_service_pb2.CommandResponse(result="")

    async def RaftMessage(self, request, context):
        """Handle raft_message requests (fire-and-forget), let any error propogate"""
        self.logger.debug(f"Processing raft message via gRPC from {context.peer()}")
        # Don't await - fire and forget
        if self.rm_wait_for_result:
            res = await self.raft_server.raft_message(request.message)
            return raft_service_pb2.MessageResponse(result=res)
        else:
            asyncio.create_task(self.raft_server.raft_message(request.message))
            return raft_service_pb2.MessageResponse(result="")

    async def DirectServerCommand(self, request, context):
        """Handle direct_server_command requests"""
        try:
            self.logger.debug(f"Processing local command via gRPC: {request.command}")
            result = await self.raft_server.direct_server_command(request.command)
            return raft_service_pb2.CommandResponse(result=json.dumps(result))
        except Exception as e:
            self.logger.error(f"Error processing local command: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return raft_service_pb2.CommandResponse(result="")


class RPCServer:
    """gRPC server implementing the Raft service interface"""
    
    def __init__(self, raft_server, rm_wait_for_result=False):
        self.raft_server = raft_server
        self.rm_wait_for_result = rm_wait_for_result
        self.server = None
        self.port = None
        # the logger is done this way to aid in testing, allowing check for caught errors
        self.logger = logging.getLogger('transport.server.grpc')

    async def start(self, port, background=False):
        if not self.server:
        
            self.port = port

            # Create gRPC server
            self.server = grpc.aio.server()

            # Add servicer
            servicer = RaftServicer(self.raft_server, self.rm_wait_for_result)
            raft_service_pb2_grpc.add_RaftServiceServicer_to_server(servicer, self.server)

            # Configure server settings for high concurrency
            listen_addr = f'localhost:{self.port}'
            self.server.add_insecure_port(listen_addr)

            # Start server
            await self.server.start()
            self.logger.info(f"gRPC server started on {listen_addr}")

            # Create task to keep server running
            self.server_task = asyncio.create_task(self.serve())

    async def serve(self):
        try:
            await self.server.wait_for_termination()
        except asyncio.CancelledError:
            self.logger.warning(f'grpc server canceled')
        finally:
            self.server_task = None
            
    async def stop(self):
        self.logger.warning("gRPC stop() called")
        
        # First cancel the server task to stop accepting new connections
        if hasattr(self, 'server_task') and self.server_task:
            self.logger.warning("cancelling server_task first")
            if not self.server_task.done():
                self.server_task.cancel()
                try:
                    await self.server_task
                    self.logger.warning("server_task cancelled and awaited")
                except asyncio.CancelledError:
                    self.logger.warning("server_task cancelled")
                    pass
            self.server_task = None
            
        # Then stop the gRPC server with extended grace period
        if self.server:
            self.logger.info(f"Shutting down gRPC server on port {self.port}")
            self.logger.warning("calling server.stop(grace=5.0)")
            
            try:
                # Use longer grace period and ensure proper cleanup
                await self.server.stop(grace=5.0)
                self.logger.warning("server.stop() completed")
                
                # Explicitly wait a moment for internal cleanup
                await asyncio.sleep(0.1)
                self.logger.warning("post-stop sleep completed")
                
            except Exception as e:
                self.logger.error(f"Error during server.stop(): {e}")
            finally:
                self.server = None
                self.logger.warning("server set to None")
                
        self.logger.warning("gRPC stop() completed")
