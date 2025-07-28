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
    server = await RunTools.make_server()
    collector,client = await RunTools.make_client()


    async def shutdown_cb(server):
        print(f'got callback, server on port {server.port} shutting down')
    await server.start(shutdown_cb)

    ct = Demo(collector)
    res = await ct.do_fresh_demo()

    # check the raft_message function
    reply = await client.raft_message('foo')
    print(f"Call to raft_message('foo') got '{reply}' in reply")

    pid = await client.direct_server_command("getpid")
    print(f"Call to direct_server_command('getpid') got {pid} in reply")
    
    ping_res = await client.direct_server_command("ping")
    print(f"Call to direct_server_command('ping') got '{ping_res}' in reply")
    
    shut_res = await client.direct_server_command("shutdown")
    print(f"shutdown request got {shut_res}")
    await client.close()
    
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
    from run_tools import RunTools
    asyncio.run(main(RunTools))
