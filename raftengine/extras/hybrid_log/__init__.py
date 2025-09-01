try:
    import lmdb
except ModuleNotFoundError: 
    raise Exception('Cannot import hybrid package, lmdb package not installed. Did you pip install raftengine[hybrid_log]?')
try:
    from raftengine.extras.lmdb_log import LmdbLog
except ModuleNotFoundError: 
    raise Exception('Cannot import hybrid_log package, lmdb_log package not installed. Did you pip install raftengine[hybrid_log]?')
try:
    from raftengine.extras.sqlite_log import SqliteLog
except ModuleNotFoundError:
    raise Exception('Cannot import hybrid_log package, sqlite_log package not installed. Did you pip install raftengine[hybrid_log]?')

from .hybrid_log import HybridLog
