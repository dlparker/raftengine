#!/usr/bin/env python
import asyncio
from pathlib import Path
import sys
this_dir = Path(__file__).resolve().parent
for parent in this_dir.parents:
    if parent.name == 'src':
        if parent not in sys.path:
            sys.path.insert(0, str(parent))
            break
else:
    raise ImportError("Could not find 'src' directory in the path hierarchy")
from base.validate_teller import validate_teller
from base.operations import Teller
from base.collector import Collector
from base.dispatcher import Dispatcher
from base.fake_rpc_pipe import FakeRPCPipe
from base.proxy import TellerWrapper


async def main():
    db_path = Path("/tmp/test_banking.db")
    if db_path.exists():
        db_path.unlink()
    teller = Teller(db_file=db_path)
    dispatcher = Dispatcher(teller)
    fake_pipe = FakeRPCPipe(dispatcher)
    collector = Collector(fake_pipe)
    await validate_teller(collector)

if __name__=="__main__":
    asyncio.run(main())
