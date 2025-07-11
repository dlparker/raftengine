import asyncio
import os
from base.setup_helper import SetupHelperAPI
from base.client import Client
from base.operations import Ops
from step4.raft_ops.proxy import ServerProxy
from step4.raft_ops.collector import Collector
from step4.raft_ops.dispatcher import Dispatcher


class SetupHelper(SetupHelperAPI):
    """
    This version uses the Collector on the client side as a ServerProxy and
    connects an async streams implementation to send packed commands to the
    server over that mechanism. The Server side async streams code sends
    the package to the Dispatcher, which dispatches to the Operations instance.
    """

    async def get_client(self, host="127.0.0.1", port=55555):
        collector = await self.get_proxy(host, port)
        return Client(server_proxy=collector)

    async def get_server(self, db_file:os.PathLike, port=55555):
        ops = Ops(db_file)
        dispatcher = Dispatcher(ops)
        as_server = ASServer(dispatcher, port)
        sock_server = await asyncio.start_server(
            as_server.handle_client, '127.0.0.1', port)
        return sock_server
    
    async def get_proxy(self, host="127.0.0.1", port=55555):
        as_client = ASClient(host, port)
        collector = Collector(as_client)
        return collector

    async def serve(self, server):
        async with server:
            await server.serve_forever()

