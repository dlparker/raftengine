try:
    import lmdb
except ModuleNotFoundError:
    raise Exception('Cannot import lmdb_log package, lmdb package not installed. Did you pip install raftengine[lmdb_log]?')

from .lmdb_log import LmdbLog
