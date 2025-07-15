"""
Async SQLite Log Implementation for Raft
Replaces synchronous sqlite3 with aiosqlite to eliminate blocking I/O operations.
"""
import abc
import os
import aiosqlite
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Union, List, Optional
import logging
from raftengine.api.log_api import LogRec, LogAPI, RecordCode
from raftengine.api.snapshot_api import SnapShot
from raftengine.api.types import ClusterConfig, NodeRec, ClusterSettings


def bool_converter(value):
    """Convert SQLite boolean values"""
    return bool(int(value)) if value is not None else False


class AsyncRecords:
    """Async version of Records class using aiosqlite"""

    def __init__(self, filepath: os.PathLike):
        # log record indexes start at 1, per raftengine spec
        self.filepath = Path(filepath).resolve()
        self.index = 0
        self.entries = []
        self.db = None
        self.term = -1
        self.voted_for = None
        self.max_index = None
        self.snapshot = None
        self._connection_pool = None

    def is_open(self):
        return self.db is not None
    
    async def open(self) -> None:
        """Open async database connection and initialize tables"""
        # Note: aiosqlite doesn't support register_converter directly
        # We'll handle boolean conversion manually
        self.db = await aiosqlite.connect(self.filepath)
        self.db.row_factory = aiosqlite.Row
        await self.ensure_tables()
        
        # Load initial state
        async with self.db.execute("SELECT * FROM stats") as cursor:
            row = await cursor.fetchone()
            if row:
                self.max_index = row['max_index']
                self.term = row['term']
                self.voted_for = row['voted_for']
            else:
                self.max_index = 0
                self.term = 0
                self.voted_for = None
                await self.db.execute(
                    "REPLACE INTO stats (dummy, max_index, term, voted_for) VALUES (?,?,?,?)",
                    [1, self.max_index, self.term, self.voted_for]
                )
                await self.db.commit()
        
        # Load snapshot if exists
        async with self.db.execute("SELECT * FROM snapshot WHERE snap_id == 1") as cursor:
            row = await cursor.fetchone()
            if row:
                self.snapshot = SnapShot(index=row['s_index'], term=row['term'])
        
    async def close(self) -> None:
        """Close async database connection"""
        if self.db is None:
            return
        await self.db.close()
        self.db = None

    async def ensure_tables(self):
        """Create database tables if they don't exist"""
        # Records table
        schema = """CREATE TABLE IF NOT EXISTS records (
            rec_index INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT,
            command TEXT,
            result TEXT,
            term INTEGER,
            error BOOLEAN,
            leader_id TEXT,
            serial TEXT,
            committed BOOLEAN,
            applied BOOLEAN
        )"""
        await self.db.execute(schema)

        # Stats table
        schema = """CREATE TABLE IF NOT EXISTS stats (
            dummy INTEGER PRIMARY KEY,
            max_index INTEGER,
            term INTEGER,
            voted_for TEXT
        )"""
        await self.db.execute(schema)

        # Nodes table
        schema = """CREATE TABLE IF NOT EXISTS nodes (
            uri TEXT PRIMARY KEY UNIQUE,
            is_adding BOOLEAN,
            is_removing BOOLEAN
        )"""
        await self.db.execute(schema)

        # Settings table
        schema = """CREATE TABLE IF NOT EXISTS settings (
            the_index INTEGER PRIMARY KEY UNIQUE,
            heartbeat_period FLOAT,
            election_timeout_min FLOAT,
            election_timeout_max FLOAT,
            max_entries_per_message INTEGER,
            use_pre_vote BOOLEAN,
            use_check_quorum BOOLEAN,
            use_dynamic_config BOOLEAN
        )"""
        await self.db.execute(schema)

        # Snapshot table
        schema = """CREATE TABLE IF NOT EXISTS snapshot (
            snap_id INTEGER PRIMARY KEY,
            s_index INTEGER NULL,
            term INTEGER NULL
        )"""
        await self.db.execute(schema)

        await self.db.commit()
                     
    async def save_entry(self, entry):
        """Save log entry to database asynchronously"""
        if self.db is None:
            await self.open()
        
        params = []
        if entry.index is not None:
            sql = """REPLACE INTO records 
                    (rec_index, code, command, result, error, term, serial, leader_id, committed, applied) 
                    VALUES (?,?,?,?,?,?,?,?,?,?)"""
            params.append(entry.index)
        else:
            sql = """INSERT INTO records 
                    (code, command, result, error, term, serial, leader_id, committed, applied) 
                    VALUES (?,?,?,?,?,?,?,?,?)"""

        params.extend([
            entry.code,
            entry.command,
            entry.result,
            entry.error,
            entry.term,
            str(entry.serial) if entry.serial else None,
            entry.leader_id,
            entry.committed,
            entry.applied
        ])
        
        async with self.db.execute(sql, params) as cursor:
            if entry.index is None:
                entry.index = cursor.lastrowid
            
            if cursor.lastrowid and cursor.lastrowid > self.max_index:
                self.max_index = cursor.lastrowid
        
        # Update stats table
        await self.db.execute(
            "REPLACE INTO stats (dummy, max_index, term, voted_for) VALUES (?,?,?,?)",
            [1, self.max_index, self.term, self.voted_for]
        )
        await self.db.commit()
        
        return await self.read_entry(entry.index)

    async def read_entry(self, index=None):
        """Read log entry from database asynchronously"""
        if self.db is None:
            await self.open()
        
        if index is None:
            async with self.db.execute("SELECT MAX(rec_index) FROM records") as cursor:
                row = await cursor.fetchone()
                index = row[0] if row and row[0] else None
                if index is None:
                    return None
        
        async with self.db.execute("SELECT * FROM records WHERE rec_index = ?", [index]) as cursor:
            rec_data = await cursor.fetchone()
            if rec_data is None:
                return None
            
            conv = dict(rec_data)
            conv['index'] = rec_data['rec_index']
            del conv['rec_index']
            if rec_data['serial']:
                conv['serial'] = int(rec_data['serial'])
            
            # Handle boolean conversion
            conv['error'] = bool_converter(conv['error'])
            conv['committed'] = bool_converter(conv['committed'])
            conv['applied'] = bool_converter(conv['applied'])
            
            log_rec = LogRec.from_dict(conv)
            return log_rec
    
    async def set_term(self, value):
        """Set current term asynchronously"""
        if self.db is None:
            await self.open()
        
        self.term = value
        await self.db.execute(
            "REPLACE INTO stats (dummy, max_index, term, voted_for) VALUES (?,?,?,?)",
            [1, self.max_index, self.term, self.voted_for]
        )
        await self.db.commit()
    
    async def set_voted_for(self, value):
        """Set voted_for field asynchronously"""
        if self.db is None:
            await self.open()
        
        self.voted_for = value
        await self.db.execute(
            "REPLACE INTO stats (dummy, max_index, term, voted_for) VALUES (?,?,?,?)",
            [1, self.max_index, self.term, self.voted_for]
        )
        await self.db.commit()
    
    async def get_entry_at(self, index):
        """Get entry at specific index"""
        if index < 1:
            return None
        return await self.read_entry(index)

    async def add_entry(self, rec: LogRec) -> LogRec:
        """Add new entry (index will be auto-assigned)"""
        rec.index = None
        rec = await self.save_entry(rec)
        return rec

    async def insert_entry(self, rec: LogRec) -> LogRec:
        """Insert/replace entry at specific index"""
        rec = await self.save_entry(rec)
        return rec

    async def get_commit_index(self):
        """Get highest committed index"""
        if self.db is None:
            await self.open()
        
        async with self.db.execute(
            "SELECT rec_index FROM records WHERE committed = 1 ORDER BY rec_index DESC LIMIT 1"
        ) as cursor:
            rec_data = await cursor.fetchone()
            if rec_data is None:
                if self.snapshot:
                    return self.snapshot.index
                return 0
            return rec_data['rec_index']

    async def get_applied_index(self):
        """Get highest applied index"""
        if self.db is None:
            await self.open()
        
        async with self.db.execute(
            "SELECT rec_index FROM records WHERE applied = 1 ORDER BY rec_index DESC LIMIT 1"
        ) as cursor:
            rec_data = await cursor.fetchone()
            if rec_data is None:
                if self.snapshot:
                    return self.snapshot.index
                return 0
            return rec_data['rec_index']

    async def delete_all_from(self, index: int):
        """Delete all entries from specified index onwards"""
        if self.db is None:
            await self.open()
        
        await self.db.execute("DELETE FROM records WHERE rec_index >= ?", [index])
        self.max_index = index - 1
        await self.db.execute(
            "REPLACE INTO stats (dummy, max_index, term, voted_for) VALUES (?,?,?,?)",
            [1, self.max_index, self.term, self.voted_for]
        )
        await self.db.commit()
    
    async def save_cluster_config(self, config: ClusterConfig) -> None:
        """Save cluster configuration asynchronously"""
        if self.db is None:
            await self.open()
        
        # Save nodes
        for node in config.nodes.values():
            await self.db.execute(
                "INSERT OR REPLACE INTO nodes (uri, is_adding, is_removing) VALUES (?,?,?)",
                [node.uri, node.is_adding, node.is_removing]
            )
        
        # Save settings
        cs = config.settings
        await self.db.execute(
            """INSERT OR REPLACE INTO settings 
               (the_index, heartbeat_period, election_timeout_min, election_timeout_max, 
                max_entries_per_message, use_pre_vote, use_check_quorum, use_dynamic_config) 
               VALUES (?,?,?,?,?,?,?,?)""",
            [1, cs.heartbeat_period, cs.election_timeout_min, cs.election_timeout_max,
             cs.max_entries_per_message, cs.use_pre_vote, cs.use_check_quorum, cs.use_dynamic_config]
        )
        await self.db.commit()
    
    async def get_cluster_config(self) -> Optional[ClusterConfig]:
        """Get cluster configuration asynchronously"""
        if self.db is None:
            await self.open()
        
        # Get settings
        async with self.db.execute("SELECT * FROM settings WHERE the_index == 1") as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None
            
            settings = ClusterSettings(
                heartbeat_period=row['heartbeat_period'],
                election_timeout_min=row['election_timeout_min'],
                election_timeout_max=row['election_timeout_max'],
                max_entries_per_message=row['max_entries_per_message'],
                use_pre_vote=bool_converter(row['use_pre_vote']),
                use_check_quorum=bool_converter(row['use_check_quorum']),
                use_dynamic_config=bool_converter(row['use_dynamic_config'])
            )

        # Get nodes
        nodes = {}
        async with self.db.execute("SELECT * FROM nodes") as cursor:
            async for row in cursor:
                rec = NodeRec(
                    uri=row['uri'],
                    is_adding=bool_converter(row['is_adding']),
                    is_removing=bool_converter(row['is_removing'])
                )
                nodes[rec.uri] = rec
        
        return ClusterConfig(nodes=nodes, settings=settings)

    def get_first_index(self):
        """Get first available index (synchronous for compatibility)"""
        if not self.snapshot:
            if self.max_index > 0:
                return 1
            return None
        if self.max_index > self.snapshot.index:
            return self.snapshot.index + 1
        return None

    def get_last_index(self):
        """Get last available index (synchronous for compatibility)"""
        if not self.snapshot:
            return self.max_index
        return max(self.max_index, self.snapshot.index)
    
    async def install_snapshot(self, snapshot):
        """Install snapshot asynchronously"""
        if self.db is None:
            await self.open()
        
        await self.db.execute("DELETE FROM snapshot")
        await self.db.execute(
            "INSERT INTO snapshot (snap_id, s_index, term) VALUES (?,?,?)",
            [1, snapshot.index, snapshot.term]
        )
        await self.db.execute("DELETE FROM records WHERE rec_index <= ?", [snapshot.index])
        await self.db.commit()
        self.snapshot = snapshot

    def get_snapshot(self):
        """Get current snapshot (synchronous for compatibility)"""
        return self.snapshot


class AsyncSqliteLog(LogAPI):
    """Async version of SqliteLog using aiosqlite for non-blocking I/O"""

    def __init__(self, filepath: os.PathLike):
        self.records = None
        self.filepath = filepath
        self.logger = logging.getLogger(__name__)

    def start(self):
        """Initialize the log storage"""
        self.records = AsyncRecords(self.filepath)
        
    async def close(self):
        """Close the log storage"""
        if self.records:
            await self.records.close()
        
    async def get_term(self) -> Union[int, None]:
        if not self.records.is_open():
            await self.records.open()
        return self.records.term
    
    async def set_term(self, value: int):
        if not self.records.is_open():
            await self.records.open()
        await self.records.set_term(value)

    async def get_voted_for(self) -> Union[int, None]:
        if not self.records.is_open():
            await self.records.open()
        return self.records.voted_for
    
    async def set_voted_for(self, value: str):
        if not self.records.is_open():
            await self.records.open()
        await self.records.set_voted_for(value)
        
    async def incr_term(self):
        if not self.records.is_open():
            await self.records.open()
        await self.records.set_term(self.records.term + 1)
        return self.records.term

    async def append(self, entry: LogRec) -> None:
        if not self.records.is_open():
            await self.records.open()
        save_rec = LogRec.from_dict(entry.__dict__)
        return_rec = await self.records.add_entry(save_rec)
        self.logger.debug("new log record %s", return_rec.index)
        return return_rec

    async def append_multi(self, entries: List[LogRec]) -> None:
        if not self.records.is_open():
            await self.records.open()
        # Process entries asynchronously but maintain order
        return_recs = []
        for entry in entries:
            return_recs.append(await self.append(entry))
        return return_recs

    async def replace(self, entry: LogRec) -> LogRec:
        if not self.records.is_open():
            await self.records.open()
        if entry.index is None:
            raise Exception("api usage error, call append for new record")
        if entry.index < 1:
            raise Exception("api usage error, cannot insert at index less than 1")
        save_rec = LogRec.from_dict(entry.__dict__)
        next_index = self.records.max_index + 1
        if save_rec.index > next_index:
            raise Exception("cannot replace record with index greater than max record index")
        await self.records.insert_entry(save_rec)
        return LogRec.from_dict(save_rec.__dict__)

    async def read(self, index: Union[int, None] = None) -> Union[LogRec, None]:
        if not self.records.is_open():
            await self.records.open()
        if index is None:
            index = self.records.max_index
        else:
            if index < 1:
                raise Exception(f"cannot get index {index}, not in records")
            if index > self.records.max_index:
                return None
        rec = await self.records.get_entry_at(index)
        if rec is None:
            return None
        return LogRec.from_dict(rec.__dict__)

    async def get_last_index(self):
        if not self.records.is_open():
            await self.records.open()
        return self.records.get_last_index()

    async def get_last_term(self):
        if not self.records.is_open():
            await self.records.open()
        rec = await self.records.read_entry()
        if rec is None:
            snap = self.records.get_snapshot()
            if snap:
                return snap.term
            return 0
        return rec.term

    async def update_and_commit(self, entry: LogRec) -> LogRec:
        entry.committed = True
        save_rec = await self.records.insert_entry(entry)
        return save_rec
    
    async def update_and_apply(self, entry: LogRec) -> LogRec:
        entry.applied = True
        save_rec = await self.records.insert_entry(entry)
        return save_rec
    
    async def get_commit_index(self):
        if not self.records.is_open():
            await self.records.open()
        return await self.records.get_commit_index()

    async def get_applied_index(self):
        if not self.records.is_open():
            await self.records.open()
        return await self.records.get_applied_index()

    async def delete_all_from(self, index: int):
        if not self.records.is_open():
            await self.records.open()
        return await self.records.delete_all_from(index)

    async def save_cluster_config(self, config: ClusterConfig) -> None:
        if not self.records.is_open():
            await self.records.open()
        return await self.records.save_cluster_config(config)
    
    async def get_cluster_config(self) -> Optional[ClusterConfig]:  
        if not self.records.is_open():
            await self.records.open()
        return await self.records.get_cluster_config()
    
    async def get_first_index(self) -> int:
        if not self.records.is_open():
            await self.records.open()
        return self.records.get_first_index()

    async def install_snapshot(self, snapshot: SnapShot):
        if not self.records.is_open():
            await self.records.open()
        return await self.records.install_snapshot(snapshot)

    async def get_snapshot(self) -> Optional[SnapShot]: 
        if not self.records.is_open():
            await self.records.open()
        return self.records.get_snapshot()