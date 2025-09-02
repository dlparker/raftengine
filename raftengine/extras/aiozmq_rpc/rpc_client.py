import aiozmq.rpc

class RPCClient:

    def __init__(self, host, port, timeout=10.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.aiozmq_conn = None
        self.aiozmq_uri = f'tcp://{self.host}:{self.port}'
        
    async def connect(self):
        raw_client = await aiozmq.rpc.connect_rpc(connect=self.aiozmq_uri)
        with raw_client.with_timeout(self.timeout) as new_client:
            self.aiozmq_conn = new_client

    async def issue_command(self, command, timeout):
        """
        This is the client side method that will take the command and send
        it to the server side. When it gets there, it will make its way
        through whatever wiring exists until it reaches the Dispatcher's
        route_command method, and then the result of that method will be
        returned through all the wiring and the RPC pipe. This is
        required for Raft support.
        """
        if self.aiozmq_conn is None:
            await self.connect()
        res = await self.aiozmq_conn.call.issue_command(command, timeout)
        if isinstance(res, dict):
            if "rpc_error" in res:
                raise Exception(res['rpc_error'])
        return res

    async def raft_message(self, message):
        """
        This is the client side method of the RPC mechanism that Raftengine
        enabled servers use to sent Raft protocol messages. This call should
        never be used by the use client code. This is required for Raft support.
        """
        if self.aiozmq_conn is None:
            await self.connect()
        res = await self.aiozmq_conn.call.raft_message(message)
        if isinstance(res, dict):
            if "rpc_error" in res:
                raise Exception(res['rpc_error'])
        return res
    
    async def direct_server_command(self, message):
        """
        This is an optional RPC that allows user clients to perform operations
        on the server that answers the RPC interface. These operations will
        not be routed through Raftengine, so any effect that they have is
        strickly on the target server. Although optional, something like this
        is almost required for any reasonable level of monitoring and control
        of server processes.
        """
        if self.aiozmq_conn is None:
            await self.connect()
        res = await self.aiozmq_conn.call.direct_server_command(message)
        if isinstance(res, dict):
            if "rpc_error" in res:
                raise Exception(res['rpc_error'])
        return res
    
    async def close(self):
        """Close the client connection"""
        if self.aiozmq_conn is not None:
            self.aiozmq_conn.close()
            await self.aiozmq_conn.wait_closed()
            self.aiozmq_conn = None
