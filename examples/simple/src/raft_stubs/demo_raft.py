#!/usr/bin/env python


async def main(RunTools):
    server = await RunTools.make_server()
    collector,client = await RunTools.make_client()
    ct = Demo(collector)
    res = await ct.do_fresh_demo()
    ping_1 = "ping_1"
    ping_1_res = await client.raft_message("ping_1")
    print(f"ping_1 message got {ping_1_res} result")
    await client.close()
    await server.stop()

    server2 = await RunTools.make_server(reload=True, port=50046)
    collector2,client2 = await RunTools.make_client(port=50046)
    ct2 = Demo(collector2)
    res = await ct2.do_reload_demo(res)
    await client2.close()
    await server2.stop()

    
    
if __name__=="__main__":
    import asyncio
    from pathlib import Path
    import sys
    src_dir = Path(__file__).parent.parent
    sys.path.insert(0, str(src_dir))
    from base.demo import Demo
    from raft_stubs.run_tools import RunTools
    
    asyncio.run(main(RunTools))
