#!/usr/bin/env python

async def main():
    storage_dir = "/tmp"
    file_path = Path(storage_dir, 'counters.pickle')
    if file_path.exists():
        file_path.unlink()
    counters = Counters(storage_dir)
    ct = Demo(counters)
    res = await ct.do_fresh_demo()
    counters2 = Counters(storage_dir)
    ct2 = Demo(counters2)
    await ct2.do_reload_demo(res)
    
    
if __name__=="__main__":
    import asyncio
    from pathlib import Path
    import sys
    src_dir = Path(__file__).parent.parent
    sys.path.insert(0, str(src_dir))
    from base.counters import Counters
    from base.demo import Demo
    asyncio.run(main())
