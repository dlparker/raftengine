#!/usr/bin/env python
import sys
import asyncio
from pathlib import Path
from aiocmd import aiocmd
from collections import defaultdict
src_dir = Path(__file__).parent.parent
logs_dir = Path(src_dir, 'logs')
sys.path.insert(0, str(logs_dir))
src_dir = Path(__file__).parent.parent
sys.path.insert(0, str(src_dir))

from admin_common import find_local_clusters, get_server_status, get_cluster_config

class MyCLI(aiocmd.PromptToolkitCmd):

    clusters = {}
    
    async def do_find_clusters(self, search_dir):
        """Discover clusters by searching directory for counter raft server working directories"""
        res = await find_local_clusters(search_dir)
        for index,key in enumerate(res.keys()):
            config = None
            cdict = res[key]
            rec = dict(discovered=cdict, config=config)
            clusters[str(index)] = rec
            rec['servers'] = servers = defaultdict(dict)
            for uri,server in cdict.items():
                status = await get_server_status(uri)
                servers[uri]['status'] = status
                servers[uri]['running'] == True if status is not None else False
                if status is not None and config is None:
                    config = await get_cluster_config(uri)
        from pprint import pprint
        pprint(clusters)
        
if __name__ == "__main__":
    asyncio.run(MyCLI().run())
