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
from astream.rpc_client import RPCClient
from base.collector import Collector
from base.test_teller import test_teller

async def main():
    port = 50050
    client = RPCClient('localhost', port)
    collector = Collector(client)
    await test_teller(collector)

if __name__=="__main__":
    asyncio.run(main())
