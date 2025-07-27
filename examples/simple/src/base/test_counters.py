#!/usr/bin/env python

async def main():
    storage_dir = "/tmp"
    file_path = Path(storage_dir, 'counters.pickle')
    if file_path.exists():
        file_path.unlink()
    counters = Counters(storage_dir)
    vt = Validator(counters)
    expected = await vt.do_test()
    counters2 = Counters(storage_dir)
    vt2 = Validator(counters2)
    await vt.do_test(expected)
    
if __name__=="__main__":
    import asyncio
    from pathlib import Path
    import sys
    src_dir = Path(__file__).parent.parent
    sys.path.insert(0, str(src_dir))
    from base.counters import Counters
    from base.validator import Validator
    asyncio.run(main())
