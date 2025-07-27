#!/usr/bin/env python
async def main(RunTools):

    helper = RPCHelper()
    server = await RunTools.make_server(helper)
    collector = await RunTools.make_client(helper)
    vt = Validator(collector)
    expected = await vt.do_test()
    await collector.pipe.close()
    await helper.stop_server_task()
    
    helper2 = RPCHelper()
    server2 = await RunTools.make_server(helper2, reload=True)
    collector2 = await RunTools.make_client(helper2)
    vt2 = Validator(collector2)
    await vt.do_test(expected)
    await collector.pipe.close()
    await helper2.stop_server_task()
    
    
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
    from rpc.rpc_helper import RPCHelper
    from run_tools import RunTools
    asyncio.run(main(RunTools))
