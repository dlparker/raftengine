from pathlib import Path
import pickle
from raftengine.api.snapshot_api import SnapShotToolAPI
from base.counters import Counters


class RaftCounters(Counters):

    async def make_snapshot(self):
        fp = Path(self.storage_dir, 'counters_snapshot.pickle')
        with open(fp, 'wb') as f:
            data = pickle.dumps(self.counts)
            f.write(data)
        print(f'\n\nsaved {self.counts} to {fp}\n\n')

    async def get_snapshot_chunk(self, offset=0):
        # We don't care what the caller thinks the offset should
        # be, since we always return the entire snapshot as one
        # chunk. The caller should not be sending us a non-zero
        # offset.
        offset = 0
        done = True
        fp = Path(self.storage_dir, 'counters_snapshot.pickle')
        if fp.exists():
            with open(self.file_path, 'rb') as f:
                data = f.read()
            return data,offset,done
        return None,offset,done

class SnapShotTool(SnapShotToolAPI):

    def __init__(self, counters, snapshot):
        self.counters = counters
        self.snapshot = snapshot
        self.new_counters = None
        
    async def load_snapshot_chunk(self, chunk) -> None:
        self.new_counters = pickle.loads(cunk)

    async def get_snapshot_chunk(self, offset=0) -> (str,int,bool):
        return await self.counters.get_snapshot_chunk(offset=0)
        
    async def apply_snapshot(self):
        self.counters.counts = self.new_counters
        await self.log.install_snapshot(self.snapshot)
