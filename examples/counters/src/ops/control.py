#!/usr/bin/env python
import asyncio
import sys
from pathlib import Path

src_dir = Path(__file__).parent.parent
sys.path.insert(0, str(src_dir))

if __name__=="__main__":
    from cluster_cmd import main
    asyncio.run(main())
