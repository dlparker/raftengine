#!/usr/bin/env python
async def main(RunTools):

    server = await RunTools.make_server()
    client = await RunTools.make_client()
    vt = Validator(client)
    expected = await vt.do_test()
    
    
if __name__=="__main__":
    import asyncio
    from pathlib import Path
    import sys
    src_dir = Path(__file__).parent.parent
    sys.path.insert(0, str(src_dir))
    from base.validator import Validator
    from raft_stubs.run_tools import RunTools
    asyncio.run(main(RunTools))
