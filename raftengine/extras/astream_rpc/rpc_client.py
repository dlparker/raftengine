import asyncio
import time
import json
import traceback
import uuid
import logging
from typing import Dict, Optional, Any


class RPCClient:
    """
    """

    def __init__(self, host, port, timeout=1.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.logger = logging.getLogger('rpc.client')
        
        # Request tracking for concurrent operations
        self.pending_requests: Dict[str, asyncio.Future] = {}
        self.response_handler_task: Optional[asyncio.Task] = None
        self.closed = False

    def get_uri(self):
        return f"astream://{self.host}:{self.port}"

    async def ensure_connection(self):
        if self.reader is None or self.writer is None:
            self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
            self.response_handler_task = asyncio.create_task(self.response_handler())
            
    async def send_request(self, message: dict) -> str:
        """
        Send a request with a unique ID and return the request ID.
        The actual response will be handled by the response handler.
        """
        last_exception = None
        
        await self.ensure_connection()
        
        # Generate unique request ID
        request_id = str(uuid.uuid4())
        message['request_id'] = request_id
        
        # Create future for this request
        future = asyncio.Future()
        self.pending_requests[request_id] = future
        
        # Send the request
        msg_str = json.dumps(message)
        msg_bytes = msg_str.encode()
        count = str(len(msg_bytes))
        
        self.writer.write(f"{count:20s}".encode())
        self.writer.write(msg_bytes)
        await self.writer.drain()
        
        return request_id
        
    async def wait_for_response(self, request_id: str, timeout: float = 30.0) -> Any:
        future = self.pending_requests[request_id]
        try:
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            # Clean up timed out request
            self.pending_requests.pop(request_id, None)
            raise asyncio.TimeoutError(f"Request {request_id} timed out after {timeout}s")

    async def issue_command(self, command, timeout=10.0) -> str:
        wrapped = {"mtype": "command", "message": command, 'timeout': timeout}
        request_id = await self.send_request(wrapped)
        timeout_plus = timeout*1.1
        self.logger.debug("Sent issue command (id=%s), awaiting response up to %f", request_id, timeout_plus)
        response = await self.wait_for_response(request_id, timeout_plus)
        # the CommandResponse object is serialized before return, then
        # the rpc_server serializes it, so unwrap it
        self.logger.debug("Got issue_command response to id=%s")
        return json.loads(response)

    async def raft_message(self, message) -> None:
        wrapped = {"mtype": "raft_message", "message": message}
        # For raft messages, we send but don't wait for response
        request_id = await self.send_request(wrapped)
        timeout_plus = self.timeout*1.1
        self.logger.debug("Sent raft message (id=%s), awaiting response up to %f", request_id, timeout_plus)
        response = await self.wait_for_response(request_id, timeout_plus)  
        result = json.loads(response)['result']
        self.logger.debug("Got raft_message response to id=%s")
        return result

    async def direct_server_command(self, command) -> str:
        wrapped = {"mtype": "direct_server_command", "message": command}
        request_id = await self.send_request(wrapped)
        timeout_plus = self.timeout*1.1
        self.logger.debug("Sent issue command (id=%s), awaiting response up to %f", request_id, timeout_plus)
        response = await self.wait_for_response(request_id, timeout_plus)
        self.logger.debug("Got direct_server_command response to id=%s")
        return json.loads(response)

    async def response_handler(self):
        try:
            error = None
            while not self.closed and self.reader is not None:
                # Read response length
                len_data = await self.reader.read(20)
                if not len_data:
                    self.logger.debug("Connection closed by server")
                    break  # Connection closed

                msg_len = int(len_data.decode().strip())

                # Read response data
                data = await self.reader.read(msg_len)
                if not data:
                    self.logger.debug("No data received, connection closed")
                    break  # Connection closed

                # Parse response
                response = json.loads(data.decode())
                request_id = response.get('request_id')
                    
                if request_id and request_id in self.pending_requests:
                    future = self.pending_requests.pop(request_id)
                    if not future.done():
                        # Check if response contains an error
                        if 'error' in response and response['error']:
                            future.set_exception(Exception(f"Server error: {response['error']}"))
                        else:
                            future.set_result(response.get('result'))
                else:
                    self.logger.warning(f"Received response for unknown request ID: {request_id}")
                    
        except Exception as e:
            error = str(e)
            self.logger.error(f"Response handler error: {e}")
            self.logger.debug(traceback.format_exc())
        finally:
            # Mark connection as broken
            self.reader = None
            self.writer = None
            self.closed = True
            if error:
                self.clear_pendings(f'connection no longer usable {error}')
            else:
                self.clear_pendings(f'connection closed')
            
    def clear_pendings(self, reason):
        # Clean up pending requests
        for request_id, future in self.pending_requests.items():
            if not future.done():
                future.set_exception(ConnectionError(reason))
        self.pending_requests.clear()
        
    async def close(self):
        self.closed = True
        
        # Cancel response handler
        if self.response_handler_task:
            self.logger.debug("close called while handler task alive, cancelling")
            self.response_handler_task.cancel()
            try:
                await self.response_handler_task
            except asyncio.CancelledError:
                pass
        
        # Close connection
        if self.writer:
            closed = False
            try:
                self.writer.close()
                closed = True
            except Exception as e:
                self.logger.warning(f"Writer close got error {e}")
            if closed:
                try:
                    await self.writer.wait_closed()
                except Exception as e:
                    self.logger.warning(f"Writer wait_closed got error {e}")
            self.writer = None
            self.reader = None
        self.clear_pendings("close")
        self.logger.debug(f"Connection to {self.host}:{self.port} closed")
