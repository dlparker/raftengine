#!/usr/bin/env python
async def main(RunTools):

    server = await RunTools.make_server()
    collector,client = await RunTools.make_client()
    async def shutdown_cb(server):
        print(f'got callback, server on port {server.port} shutting down')
    await server.start(shutdown_cb)
    vt = Validator(collector)
    expected = await vt.do_test()
    await collector.pipe.close()
    await server.stop()
    server2 = await RunTools.make_server(reload=True)
    await server2.start(shutdown_cb)
    collector2,client2 = await RunTools.make_client()
    vt2 = Validator(collector2)
    await vt2.do_test(expected)
    await collector2.pipe.close()
    await server2.stop()
    
    
if __name__=="__main__":
    import asyncio
    from pathlib import Path
    import sys
    src_dir = Path(__file__).parent.parent
    sys.path.insert(0, str(src_dir))
    from base.counters import Counters
    from base.validator import Validator
    from split_base.collector import Collector
    from split_base.dispatcher import Dispatcher
    from run_tools import RunTools
    asyncio.run(main(RunTools))
