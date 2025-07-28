#!/usr/bin/env python
import asyncio
from pathlib import Path
import sys
src_dir = Path(__file__).parent.parent
sys.path.insert(0, str(src_dir))
from raftengine.deck.log_control import LogController
log_controller = LogController.make_controller()
from run_tools import Cluster
from split_base.collector import Collector
from base.validator import Validator

async def main(cluster):

    cluster.setup_servers()
    await cluster.start_servers()
    client_0 = cluster.get_client(index=0)
    pid = await client_0.direct_server_command("getpid")
    print(f"Call to server 0 direct_server_command('getpid') got {pid} in reply")
    client_1 = cluster.get_client(index=1)
    pid = await client_1.direct_server_command("getpid")
    print(f"Call to server 1 direct_server_command('getpid') got {pid} in reply")
    client_2 = cluster.get_client(index=2)
    pid = await client_2.direct_server_command("getpid")
    print(f"Call to server 2 direct_server_command('getpid') got {pid} in reply")
    collector = Collector(client_0)
    res = await client_0.direct_server_command("take_power")
    print(f"Call to server 0 direct_server_command('take_power') got '{res}' in reply")
    vt = Validator(collector)
    expected = await vt.do_test()
    await cluster.stop_servers()
    
    
if __name__=="__main__":
    asyncio.run(main(Cluster(clear=True)))
