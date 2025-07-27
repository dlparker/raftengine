import asyncio
from pathlib import Path
from base.counters import Counters
from base.validator import Validator
from split_base.collector import Collector
from split_base.dispatcher import Dispatcher
from split_base.pipe import FakeRPCPipe

class RunTools:
    @staticmethod
    async def make_server(helper, reload=False):
        storage_dir = "/tmp"
        file_path = Path(storage_dir, 'counters.pickle')
        if file_path.exists() and not reload:
            file_path.unlink()
        counters = Counters(storage_dir)
        dispatcher = Dispatcher(counters)
        server = await helper.get_rpc_server(50040, dispatcher)
        await helper.start_server_task()
        return server

    @staticmethod
    async def make_client(helper):
        rpc_client = await helper.rpc_client_maker('localhost', 50040)
        collector = Collector(rpc_client)
        return collector
