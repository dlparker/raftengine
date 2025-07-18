import asyncio
import time
import json
import traceback
import uuid
import logging
from typing import Dict, Optional, Any
from base.rpc_api import RPCAPI
from raftengine.api.deck_api import CommandResult

logger = logging.getLogger('bank.transport.client.astream')

class RPCClient(RPCAPI):
    """
    Concurrent RPC client that supports overlapping RPCs.
    
    Unlike the original RPCClient, this version allows multiple RPCs to be
    in flight simultaneously by using request IDs to match responses to requests.
    """

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        
        # Request tracking for concurrent operations
        self.pending_requests: Dict[str, asyncio.Future] = {}
        self.response_handler_task: Optional[asyncio.Task] = None
        self.connection_lock = asyncio.Lock()
        self.closed = False

    def get_uri(self):
        return f"astream://{self.host}:{self.port}"

    async def _ensure_connection(self):
        """Ensure connection is established"""
        async with self.connection_lock:
            if self.reader is None or self.writer is None:
                try:
                    logger.debug(f"Establishing connection to {self.host}:{self.port}")
                    self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
                    logger.info(f"Connected to {self.host}:{self.port}")
                    # Start response handler task
                    if self.response_handler_task is None or self.response_handler_task.done():
                        self.response_handler_task = asyncio.create_task(self._response_handler())
                except Exception as e:
                    self.reader = None
                    self.writer = None
                    raise e

    async def _response_handler(self):
        """Background task to handle incoming responses and match them to requests"""
        try:
            while not self.closed and self.reader is not None:
                try:
                    # Read response length
                    len_data = await self.reader.read(20)
                    if not len_data:
                        logger.debug("Connection closed by server")
                        break  # Connection closed
                    
                    msg_len = int(len_data.decode().strip())
                    
                    # Read response data
                    data = await self.reader.read(msg_len)
                    if not data:
                        logger.debug("No data received, connection closed")
                        break  # Connection closed
                    
                    # Parse response
                    response = json.loads(data.decode())
                    request_id = response.get('request_id')
                    
                    if request_id and request_id in self.pending_requests:
                        # Match response to pending request
                        future = self.pending_requests.pop(request_id)
                        if not future.done():
                            # Check if response contains an error
                            if 'error' in response and response['error']:
                                future.set_exception(Exception(f"Server error: {response['error']}"))
                            else:
                                future.set_result(response.get('result'))
                    else:
                        logger.warning(f"Received response for unknown request ID: {request_id}")
                    
                except asyncio.CancelledError:
                    break
                except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                    # Connection was reset/broken, break the loop
                    # Only log if we're not closing
                    if not self.closed:
                        logger.debug("Connection was reset by peer")
                    break
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON in response: {e}")
                    continue  # Try to continue processing other responses
                except Exception as e:
                    # Handle other errors - could be a malformed response
                    logger.error(f"Error in response handler: {e}")
                    logger.debug(traceback.format_exc())
                    # Don't break on other errors, try to continue
                    
        except Exception as e:
            logger.error(f"Response handler error: {e}")
            logger.debug(traceback.format_exc())
        finally:
            # Mark connection as broken
            self.reader = None
            self.writer = None
            
            # Clean up pending requests
            for request_id, future in self.pending_requests.items():
                if not future.done():
                    future.set_exception(ConnectionError("Connection closed"))
            self.pending_requests.clear()

    async def _send_request(self, message: dict, retry_count: int = 1) -> str:
        """
        Send a request with a unique ID and return the request ID.
        The actual response will be handled by the response handler.
        """
        last_exception = None
        
        for attempt in range(retry_count + 1):
            try:
                await self._ensure_connection()
                
                # Generate unique request ID
                request_id = str(uuid.uuid4())
                message['request_id'] = request_id
                
                # Create future for this request
                future = asyncio.Future()
                self.pending_requests[request_id] = future
                
                try:
                    # Send the request
                    msg_str = json.dumps(message)
                    msg_bytes = msg_str.encode()
                    count = str(len(msg_bytes))
                    
                    self.writer.write(f"{count:20s}".encode())
                    self.writer.write(msg_bytes)
                    await self.writer.drain()
                    
                    return request_id
                    
                except Exception as e:
                    # Clean up on send failure
                    self.pending_requests.pop(request_id, None)
                    if not future.done():
                        future.set_exception(e)
                    raise
                    
            except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, OSError) as e:
                last_exception = e
                
                # Only log connection errors if not a raft message (which are fire-and-forget)
                if message.get('mtype') != 'raft_message':
                    logger.warning(f"Connection error on attempt {attempt + 1}: {e}")
                
                # Reset connection for retry
                self.reader = None
                self.writer = None
                if self.response_handler_task:
                    self.response_handler_task.cancel()
                    self.response_handler_task = None
                
                if attempt < retry_count:
                    if message.get('mtype') != 'raft_message':
                        logger.info(f"Retrying connection in {0.1 * (attempt + 1)}s...")
                    await asyncio.sleep(0.1 * (attempt + 1))  # Exponential backoff
                
        # If we get here, all retries failed
        raise last_exception or ConnectionError("Failed to send request after retries")

    async def _wait_for_response(self, request_id: str, timeout: float = 30.0) -> Any:
        """Wait for response to a specific request ID"""
        if request_id not in self.pending_requests:
            raise ValueError(f"No pending request with ID {request_id}")
        
        future = self.pending_requests[request_id]
        try:
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            # Clean up timed out request
            self.pending_requests.pop(request_id, None)
            raise asyncio.TimeoutError(f"Request {request_id} timed out after {timeout}s")

    async def send_message(self, message: str) -> str:
        """
        Send a raw message and wait for response.
        This maintains compatibility with the original interface.
        """
        # Wrap the string message in our protocol format
        wrapped = {"mtype": "raw_message", "message": message}
        request_id = await self._send_request(wrapped)
        response = await self._wait_for_response(request_id)
        return response

    async def run_command(self, command) -> CommandResult:
        """Send a command and wait for response"""
        wrapped = {"mtype": "command", "message": command}
        request_id = await self._send_request(wrapped)
        response = await self._wait_for_response(request_id)
        
        if isinstance(response, dict) and 'error' in response:
            raise Exception(f"Server error: {response['error']}")
        
        result = CommandResult(**json.loads(response)) if isinstance(response, str) else CommandResult(**response)
        return result

    async def raft_message(self, message) -> None:
        """
        Send a raft message. These are fire-and-forget.
        For concurrent version, we still send with request ID but don't wait for response.
        """
        wrapped = {"mtype": "raft_message", "message": message}
        # For raft messages, we send but don't wait for response
        try:
            # Don't retry for raft messages - they're fire-and-forget
            request_id = await self._send_request(wrapped, retry_count=0)
            # Create a task to wait for the response but don't await it
            # This ensures proper cleanup of the request tracking
            async def cleanup_raft_response():
                try:
                    await self._wait_for_response(request_id, timeout=1.0)  # Shorter timeout
                except:
                    pass  # Raft messages are fire-and-forget
            
            asyncio.create_task(cleanup_raft_response())
        except Exception:
            # Raft messages are fire-and-forget, so we don't propagate errors
            # Don't log connection errors for raft messages during shutdown
            pass
        
        return None

    async def local_command(self, command) -> str:
        """Send a local command and wait for response"""
        wrapped = {"mtype": "local_command", "message": command}
        request_id = await self._send_request(wrapped)
        response = await self._wait_for_response(request_id)
        return response

    async def close(self):
        """Close the connection and clean up"""
        logger.debug(f"Closing connection to {self.host}:{self.port}")
        self.closed = True
        
        # Cancel response handler
        if self.response_handler_task:
            self.response_handler_task.cancel()
            try:
                await self.response_handler_task
            except asyncio.CancelledError:
                pass
        
        # Close connection
        if self.writer:
            self.writer.close()
            try:
                await self.writer.wait_closed()
            except:
                pass
            self.writer = None
            self.reader = None
        
        # Clean up pending requests
        pending_count = len(self.pending_requests)
        if pending_count > 0:
            logger.warning(f"Cleaning up {pending_count} pending requests")
        
        for future in self.pending_requests.values():
            if not future.done():
                future.set_exception(ConnectionError("Client closed"))
        self.pending_requests.clear()
        
        logger.debug(f"Connection to {self.host}:{self.port} closed")

    async def __aenter__(self):
        """Async context manager entry"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()
