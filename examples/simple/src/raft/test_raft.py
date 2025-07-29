#!/usr/bin/env python
import asyncio
from pathlib import Path
import sys
import argparse
import traceback
src_dir = Path(__file__).parent.parent
sys.path.insert(0, str(src_dir))
from raftengine.deck.log_control import LogController
log_controller = LogController.make_controller()
from run_tools import Cluster
from split_base.collector import Collector
from base.validator import Validator

async def main(args):
    cluster = Cluster(transport=args.transport, base_port=args.base_port)
    started_servers = False
    try:
        client_0 = cluster.get_client(index=0)
        pid = await client_0.direct_server_command("getpid")
        print(f"Call to server 0 direct_server_command('getpid') got {pid} in reply, not starting servers")
    except:
        traceback.format_exc()
        await cluster.start_servers()
        started_servers = True
        await asyncio.sleep(0.1)
        res = await client_0.direct_server_command("take_power")
        print(f"Call to server 0 direct_server_command('take_power') got '{res}' in reply")
    collector = Collector(client_0)
    vt = Validator(collector)
    expected = await vt.do_test()
    await cluster.stop_servers()
    
    
if __name__=="__main__":
    parser = argparse.ArgumentParser(description='Raft Cluster Performance Testing Tool')
    parser.add_argument('-b', '--base_port', type=int, default=59090,
                        help='Port number for first node in cluster')
    parser.add_argument('--transport', '-t', 
                        choices=['astream', 'aiozmq', 'fastapi',],
                        default='aiozmq',
                        help='Transport mechanism to use')
    args = parser.parse_args()
    asyncio.run(main(args))
