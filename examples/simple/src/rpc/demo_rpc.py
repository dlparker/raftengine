#!/usr/bin/env python


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

async def make_client(helper):
    rpc_client = await helper.rpc_client_maker('localhost', 50040)
    collector = Collector(rpc_client)
    return collector

async def main(RunTools):
    helper = RPCHelper()
    server = await RunTools.make_server(helper)
    collector = await RunTools.make_client(helper)
    ct = Demo(collector)
    res = await ct.do_fresh_demo()
    await collector.pipe.close()
    await helper.stop_server_task()

    helper2 = RPCHelper()
    server2 = await RunTools.make_server(helper2, reload=True)
    collector2 = await RunTools.make_client(helper2)
    ct2 = Demo(collector2)
    await ct2.do_reload_demo(res)
    await collector.pipe.close()
    await helper2.stop_server_task()
    
    
if __name__=="__main__":
    import asyncio
    from pathlib import Path
    import sys
    src_dir = Path(__file__).parent.parent
    sys.path.insert(0, str(src_dir))
    from base.counters import Counters
    from base.demo import Demo
    from split_base.collector import Collector
    from split_base.dispatcher import Dispatcher
    from rpc.rpc_helper import RPCHelper
    from run_tools import RunTools
    asyncio.run(main(RunTools))
