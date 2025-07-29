#!/usr/bin/env python


async def main(RunTools, args):
    rt = RunTools(args.transport)
    server = await rt.make_server()
    collector,client = await rt.make_client()

    async def shutdown_cb(server):
        print(f'got callback, server on port {server.port} shutting down')
    await server.start(shutdown_cb)
    await asyncio.sleep(0.001)
    vt = Validator(collector)
    expected = await vt.do_test()
    await collector.pipe.close()
    await server.stop()
    
    
if __name__=="__main__":
    import asyncio
    from pathlib import Path
    import sys
    import argparse
    src_dir = Path(__file__).parent.parent
    sys.path.insert(0, str(src_dir))
    from base.counters import Counters
    from base.validator import Validator
    from split_base.collector import Collector
    from split_base.dispatcher import Dispatcher
    parser = argparse.ArgumentParser(description='RPC simple test tool')
    parser.add_argument('--transport', '-t', 
                        choices=['astream', 'aiozmq', 'fastapi',],
                        default='aiozmq',
                        help='Transport mechanism to use')
    args = parser.parse_args()
    from rpc.run_tools import RunTools
    asyncio.run(main(RunTools, args))
