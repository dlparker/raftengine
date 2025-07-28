#!/usr/bin/env python
async def main(RunTools):

    server = await RunTools.make_server()
    collector,client = await RunTools.make_client()
    vt = Validator(collector)
    expected = await vt.do_test()
    await client.close()
    await server.stop()

    server2 = await RunTools.make_server(reload=True, port=50046)
    collector2,client2 = await RunTools.make_client(port=50046)
    vt2 = Validator(collector2)
    await vt2.do_test(expected)
    await client2.close()
    await server2.stop()

    
    
if __name__=="__main__":
    import asyncio
    from pathlib import Path
    import sys
    src_dir = Path(__file__).parent.parent
    sys.path.insert(0, str(src_dir))
    from base.validator import Validator
    from raft_stubs.run_tools import RunTools
    asyncio.run(main(RunTools))
