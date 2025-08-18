import asyncio
import traceback
import json
from typing import Set
import logging
logger = logging.getLogger('transport.server.astream')

class RPCServer:
    """
    Concurrent RPC server that supports overlapping RPCs.

    """

    def __init__(self, raft_server):
        self.raft_server = raft_server
        self.active_connections = set()
        self.shutdown_event = asyncio.Event()
        self.port = None
        self.server_task = None
        self.sock_server = None

    def get_raft_server(self):
        return self.raft_server

    async def start(self, port):
        if self.sock_server:
            return
        self.port = port
        self.sock_server = await asyncio.start_server(
            self.handle_client, '0.0.0.0', self.port
        )
        async def serve():
            logger.info(f"server running on port {self.port}")
            try:
                # Keep the server running
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                # Server is being shut down
                pass
            finally:
                if self.sock_server:
                    self.sock_server.close()
                    try:
                        await self.sock_server.wait_closed()
                        self.sock_server = None
                    except asyncio.CancelledError:
                        pass
                    finally:
                        self.sock_server = None
                self.server_task = None
        self.server_task = asyncio.create_task(serve())
                
    async def stop(self):
        if self.server_task:
            self.server_task.cancel()
            try:
                await self.server_task
            except asyncio.CancelledError:
                pass
            self.server_task = None
        if self.sock_server:
            self.sock_server.close()
            try:
                await self.sock_server.wait_closed()
            except asyncio.CancelledError:
                pass
            self.sock_server = None
    
    async def handle_client(self, reader, writer):
        """Handle a new client connection"""
        info = writer.get_extra_info("peername")
        logger.info(f"New client connection from {info}")
        cf = ClientFollower(self, reader, writer)
        
        # Track this connection
        self.active_connections.add(cf)
        
        try:
            await cf.run()
        finally:
            # Remove from tracking
            self.active_connections.discard(cf)
            logger.debug(f"Client connection from {info} closed")
    
    async def shutdown(self):
        """Gracefully shutdown the server"""
        logger.warning("Server shutdown initiated")
        self.shutdown_event.set()
        
        # Close all active connections
        connection_count = len(self.active_connections)
        if connection_count > 0:
            logger.info(f"Closing {connection_count} active connections")
        
        for connection in list(self.active_connections):
            try:
                await connection.cleanup()
            except Exception:
                pass  # Ignore errors during shutdown
        
        self.active_connections.clear()
        logger.info("Server shutdown complete")


class ClientFollower:
    """
    Handles a single client connection with support for concurrent request processing.
    
    Each incoming request is processed in its own asyncio task, allowing multiple
    requests to be handled simultaneously while maintaining proper response matching.
    """

    def __init__(self, rpc_server: RPCServer, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.rpc_server = rpc_server
        self.reader = reader
        self.writer = writer
        self.raft_server = rpc_server.get_raft_server()
        self.info = writer.get_extra_info("peername")
        
        # Track active request tasks for proper cleanup
        self.active_tasks: Set[asyncio.Task] = set()
        self.write_lock = asyncio.Lock()  # Protect concurrent writes to the same connection

    async def send_response(self, response_data: dict):
        """Send a response back to the client"""
        async with self.write_lock:
            try:
                result = json.dumps(response_data, default=lambda o: o.__dict__)
                response = result.encode()
                count = str(len(response))
                self.writer.write(f"{count:20s}".encode())
                self.writer.write(response)
                await self.writer.drain()
            except Exception as e:
                logger.error(f"Error sending response to {self.info}: {e}")
                logger.debug(traceback.format_exc())

    async def process_request(self, request: dict, request_id: str):
        """Process a single request in its own task"""
        try:
            mtype = request.get('mtype')
            message = request.get('message')
            timeout = request.get('timeout', 10.0)
            if mtype == "command":
                result = await self.issue_command(message, timeout)
            elif mtype == "direct_server_command":
                result = await self.direct_server_command(message)
            elif mtype == "raft_message":
                result = await self.raft_message(message)
            else:
                result = json.dumps({"result": None, "error": f"Unknown message type: {mtype}"})
            
            # Send response with request ID
            response_data = {
                "result": result,
                "request_id": request_id
            }
            await self.send_response(response_data)
            
        except Exception as e:
            # Send error response with request ID
            error_response = {
                "result": None,
                "error": traceback.format_exc(),
                "request_id": request_id
            }
            await self.send_response(error_response)

    async def issue_command(self, command, timeout):
        """Process a command request"""
        raw_result = await self.raft_server.issue_command(command, timeout)
        result = json.dumps(raw_result, default=lambda o: o.__dict__)
        return result

    async def direct_server_command(self, command):
        raw_result = await self.raft_server.direct_server_command(command)
        result = json.dumps(raw_result, default=lambda o: o.__dict__)
        return result

    async def raft_message(self, message):
        """Process a raft message request"""
        # We don't wait for the response, gets tricky with overlapping calls
        asyncio.create_task(self.raft_server.raft_message(message))
        result = json.dumps(dict(result=None))
        return result

    def cleanup_task(self, task: asyncio.Task):
        """Clean up completed tasks"""
        self.active_tasks.discard(task)

    async def run(self):
        """Main connection handling loop"""
        counter = 0
        try:
            while not self.rpc_server.shutdown_event.is_set():
                try:
                    # Use a timeout for read operations to check shutdown periodically
                    try:
                        len_data = await asyncio.wait_for(self.reader.read(20), timeout=1.0)
                    except asyncio.TimeoutError:
                        # Timeout - check if we should shutdown
                        continue
                    counter += 1 
                    if not len_data:
                        break  # Connection closed
                    
                    msg_len = int(len_data.decode().strip())
                    
                    # Read message data
                    data = await self.reader.read(msg_len)
                    if not data:
                        break  # Connection closed
                    
                    # Parse the request
                    request = json.loads(data.decode())
                    request_id = request.get('request_id')
                    
                    # Handle backward compatibility for messages without request IDs
                    if request_id is None:
                        # Generate a request ID for backward compatibility
                        import uuid
                        request_id = str(uuid.uuid4())
                    
                    # Process request concurrently
                    task = asyncio.create_task(self.process_request(request, request_id))
                    self.active_tasks.add(task)
                    
                    # Set up task cleanup
                    task.add_done_callback(self.cleanup_task)
                    
                except asyncio.CancelledError:
                    # Server is shutting down, exit gracefully
                    break
                except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                    # Connection was reset by peer, exit gracefully without error logging
                    break
                except Exception as e:
                    # Log error but continue processing other requests
                    # Be careful with traceback.print_exc() during shutdown
                    try:
                        if not self.rpc_server.shutdown_event.is_set():
                            logger.error(f"Error processing request from {self.info}: {e}")
                            if "Unterminated" in str(e):
                                with open(f'/tmp/error_{counter}.txt', 'w') as f:
                                    f.write(data)
                            if not asyncio.current_task().cancelled():
                                logger.debug(traceback.format_exc())
                    except:
                        # If even error logging fails (e.g., during shutdown), just break
                        break
                    
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            # Connection errors during shutdown are expected, exit gracefully
            pass
        except Exception as e:
            # Only log if we're not being cancelled or shutting down
            try:
                if not asyncio.current_task().cancelled() and not self.rpc_server.shutdown_event.is_set():
                    logger.error(f"Connection error with {self.info}: {e}")
                    logger.debug(traceback.format_exc())
            except:
                # Ignore errors during error logging
                pass
        finally:
            await self.cleanup()

    async def cleanup(self):
        """Clean up the connection and cancel active tasks"""
        # Cancel all active tasks
        for task in list(self.active_tasks):
            if not task.done():
                task.cancel()
        
        # Wait for tasks to complete cancellation
        if self.active_tasks:
            try:
                await asyncio.wait(self.active_tasks, timeout=1.0)
            except asyncio.TimeoutError:
                pass  # Some tasks might not cancel cleanly
            except Exception:
                pass  # Ignore errors during cleanup
        
        # Close the writer
        try:
            if not self.writer.is_closing():
                self.writer.close()
                try:
                    await self.writer.wait_closed()
                except asyncio.CancelledError:
                    pass
                except Exception:
                    pass  # Ignore errors during connection closing
        except Exception:
            pass  # Ignore all errors during writer cleanup

    def __del__(self):
        """Ensure cleanup on garbage collection"""
        if hasattr(self, 'active_tasks') and self.active_tasks:
            # Cancel any remaining tasks
            for task in self.active_tasks:
                if not task.done():
                    task.cancel()
