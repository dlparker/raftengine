from pathlib import Path
import pickle
import base64
from raftengine.api.snapshot_api import SnapShotToolAPI
from base.counters import Counters


class RaftCounters(Counters):

    def __init__(self, log):
        self.log = log
    
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

    def get_snapshot_tool(self, snapshot):
        return SnapShotTool(self, snapshot)
    
class SnapShotTool(SnapShotToolAPI):

    def __init__(self, counters, snapshot):
        self.counters = counters
        self.snapshot = snapshot
        self.new_counters = None
        
    async def load_snapshot_chunk(self, chunk) -> None:
        # this comes in over the wrire, so it is base64 string
        msgbytes = chunk.encode('utf-8')
        chunk_bytes =  base64.b64decode(msgbytes)
        self.new_counters = pickle.loads(chunk_bytes)

    async def get_snapshot_chunk(self, offset=0) -> (str,int,bool):
        chunk,offset,done = await self.counters.get_snapshot_chunk(offset=0)
        # this is for export so it needs to be a string, not binary, so base64 encode it
        base64_bytes = base64.b64encode(chunk)
        base64_string = base64_bytes.decode('utf-8')
        return base64_string, offset, done
        
    async def apply_snapshot(self):
        self.counters.counts = self.new_counters
        return self.snapshot()
