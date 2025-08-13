#!/usr/bin/env python

def make_server(reload=False):
    storage_dir = "/tmp"
    file_path = Path(storage_dir, 'counters.pickle')
    counters = Counters(storage_dir)
    dispatcher = Dispatcher(counters)
    return dispatcher

def make_client(dispatcher):

    pipe = FakeRPCPipe(dispatcher)
    collector = Collector(pipe)
    return collector


async def main():
    dispatcher = make_server()
    collector = make_client(dispatcher)
    vt = Validator(collector)
    expected = await vt.do_test()
    
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
    from split_base.pipe import FakeRPCPipe
    asyncio.run(main())
