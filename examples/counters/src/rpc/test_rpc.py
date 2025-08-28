#!/usr/bin/env python
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
from rpc.run_tools import RunTools


async def main():
    rt = RunTools()
    server = await rt.make_server()
    collector,client = await rt.make_client()

    async def shutdown_cb(server):
        print(f'got callback, server on port {server.port} shutting down')
    await server.start(shutdown_cb)
    await asyncio.sleep(0.001)

    vt = Validator(collector)
    expected = await vt.do_test()
    
    # Shutdown server gracefully using the same pattern as demo_rpc.py
    shut_res = await client.direct_server_command("shutdown")
        
    await client.close()
    
    
if __name__=="__main__":
    asyncio.run(main())

