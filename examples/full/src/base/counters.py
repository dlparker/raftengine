import string
from collections import defaultdict
from pathlib import Path
import pickle
    
class Counters:

    def __init__(self, storage_dir):
        self.storage_dir = storage_dir
        self.file_path = Path(storage_dir, 'counters.pickle')
        if self.file_path.exists():
            try:
                with open(self.file_path, 'rb') as f:
                    data = f.read()
                    self.counts = pickle.loads(data)
            except:
                self.counts = defaultdict(int)
        else:
            self.counts = defaultdict(int)

    def save(self):
        with open(self.file_path, 'wb') as f:
            data = pickle.dumps(self.counts)
            f.write(data)

    async def counter_add(self, name, value):
        if len(name) != 1 or name[0] not in string.ascii_letters:
            raise Exception('Counter names must be a single ascii letter')
        self.counts[name] += value
        self.save()
        return self.counts[name]

    async def get_counters(self):
        return dict(self.counts)

