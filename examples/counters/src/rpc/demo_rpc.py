#!/usr/bin/env python


async def main(RunTools, args):
    rt = RunTools()
    server = await rt.make_server()
    collector,client = await rt.make_client()

    async def shutdown_cb(server):
        print(f'got callback, server on port {server.port} shutting down')
    await server.start(shutdown_cb)
    await asyncio.sleep(0.001)
    pid = await client.direct_server_command("getpid")
    print(f"Call to direct_server_command('getpid') got {pid} in reply")

    ct = Demo(collector)
    res = await ct.do_unknown_state_demo()

    # check the raft_message function
    reply = await client.raft_message('foo')
    print(f"Call to raft_message('foo') got '{reply}' in reply")

    pid = await client.direct_server_command("getpid")
    print(f"Call to direct_server_command('getpid') got {pid} in reply")
    
    ping_res = await client.direct_server_command("ping")
    print(f"Call to direct_server_command('ping') got '{ping_res}' in reply")
    

    shut_res = await client.direct_server_command("shutdown")
    print(f"shutdown request got {shut_res}")

    print('closing client')
    await client.close()
    
    
if __name__=="__main__":
    import asyncio
    from pathlib import Path
    import sys
    import argparse
    src_dir = Path(__file__).parent.parent
    sys.path.insert(0, str(src_dir))
    from base.counters import Counters
    from base.demo import Demo
    from split_base.collector import Collector
    from split_base.dispatcher import Dispatcher
    parser = argparse.ArgumentParser(description='RPC simple test tool')
    parser.add_argument('--transport', '-t', 
                        choices=['astream', 'aiozmq', 'grpc'],
                        default='aiozmq',
                        help='Transport mechanism to use')
    args = parser.parse_args()
    from run_tools import RunTools
    asyncio.run(main(RunTools, args))
