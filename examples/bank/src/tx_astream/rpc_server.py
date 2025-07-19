import asyncio
import traceback
import json
from typing import Set
from raftengine.deck.log_control import LogController
log_controller = LogController.get_controller()
logger = log_controller.add_logger('transport.server.astream')


class RPCServer:
    """
    Concurrent RPC server that supports overlapping RPCs.
    
    Unlike the original RPCServer, this version processes each request
    in its own asyncio task, allowing multiple requests to be handled
    concurrently per client connection.
    """

    def __init__(self, raft_server):
        self.raft_server = raft_server
        self.active_connections = set()
        self.shutdown_event = asyncio.Event()

    def get_raft_server(self):
        return self.raft_server
    
    async def handle_client(self, reader, writer):
        """Handle a new client connection"""
        info = writer.get_extra_info("peername")
        logger.info(f"New client connection from {info}")
        cf = ClientFollower(self, reader, writer)
        
        # Track this connection
        self.active_connections.add(cf)
        
        try:
            await cf.go()
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
            
            if mtype == "command":
                result = await self.do_command(message)
            elif mtype == "local_command":
                result = await self.local_command(message)
            elif mtype == "raft_message":
                result = await self.do_raft(message)
            elif mtype == "raw_message":
                # Handle raw message for backward compatibility
                result = message
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

    async def do_command(self, command):
        """Process a command request"""
        raw_result = await self.raft_server.run_command(command)
        result = json.dumps(raw_result, default=lambda o: o.__dict__)
        return result

    async def local_command(self, command):
        """Process a local command request"""
        raw_result = await self.raft_server.local_command(command)
        result = json.dumps(raw_result, default=lambda o: o.__dict__)
        return result

    async def do_raft(self, message):
        """Process a raft message request"""
        # We don't wait for the response, gets tricky with overlapping calls
        asyncio.create_task(self.raft_server.raft_message(message))
        result = json.dumps(dict(result=None))
        return result

    def cleanup_task(self, task: asyncio.Task):
        """Clean up completed tasks"""
        self.active_tasks.discard(task)

    async def go(self):
        """Main connection handling loop"""
        try:
            while not self.rpc_server.shutdown_event.is_set():
                try:
                    # Use a timeout for read operations to check shutdown periodically
                    try:
                        len_data = await asyncio.wait_for(self.reader.read(20), timeout=1.0)
                    except asyncio.TimeoutError:
                        # Timeout - check if we should shutdown
                        continue
                    
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
