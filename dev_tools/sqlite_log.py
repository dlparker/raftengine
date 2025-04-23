import abc
import os
import sqlite3
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Union, List, Optional
import logging
from raftengine.api.log_api import LogRec, LogAPI, RecordCode
from raftengine.api.types import ClusterConfig, NodeRec, ClusterSettings

def bool_converter(value):
    return bool(int(value))

class Records:

    def __init__(self, filepath: os.PathLike):
        # log record indexes start at 1, per raftengine spec
        self.filepath = Path(filepath).resolve()
        self.index = 0
        self.entries = []
        self.db = None
        self.term = -1
        self.voted_for = None
        self.max_index = -1
        # Don't call open from here, we may be in the wrong thread,
        # at least in testing. Maybe in real server if threading is used.
        # Let it get called when the running server is trying to use it.

    def is_open(self):
        return self.db is not None
    
    def open(self) -> None:
        sqlite3.register_converter('BOOLEAN', bool_converter)
        self.db = sqlite3.connect(self.filepath,
                                  detect_types=sqlite3.PARSE_DECLTYPES |
                                  sqlite3.PARSE_COLNAMES)
        self.db.row_factory = sqlite3.Row
        self.ensure_tables()
        cursor = self.db.cursor()
        sql = "select * from stats"
        cursor.execute(sql)
        row = cursor.fetchone()
        if row:
            self.max_index = row['max_index']
            self.term = row['term']
            self.voted_for = row['voted_for']
        else:
            self.max_index = 0
            self.term = 0
            self.voted_for = None
            sql = "replace into stats (dummy, max_index, term, voted_for)" \
                " values (?,?,?,?)"
            cursor.execute(sql, [1, self.max_index, self.term, self.voted_for])
        
    def close(self) -> None:
        if self.db is None:  # pragma: no cover
            return  # pragma: no cover
        self.db.close()
        self.db = None

    def ensure_tables(self):
        cursor = self.db.cursor()
        schema =  "CREATE TABLE if not exists records " 
        schema += "(rec_index INTEGER primary key, " 
        schema += "code TEXT, " 
        schema += "command TEXT, " 
        schema += "result TEXT, "
        schema += "term int, "
        schema += "error BOOLEAN, " 
        schema += "leader_id TEXT, "
        schema += "serial TEXT, "
        schema += "committed BOOLEAN," 
        schema += "applied BOOLEAN)" 
        cursor.execute(schema)
        schema = f"CREATE TABLE if not exists stats " \
            "(dummy INTERGER primary key, max_index INTEGER," \
            " term INTEGER, voted_for TEXT)"
        cursor.execute(schema)
        schema =  "CREATE TABLE if not exists nodes " 
        schema += "(uri TEXT PRIMARY KEY UNIQUE, " 
        schema += "is_adding BOOLEAN, " 
        schema += "is_removing BOOLEAN, " 
        schema += "is_loading BOOLEAN)" 
        cursor.execute(schema)
        schema =  "CREATE TABLE if not exists settings " 
        schema += "(the_index INTEGER PRIMARY KEY UNIQUE, " 
        schema += "heartbeat_period FLOAT, " 
        schema += "election_timeout_min FLOAT, " 
        schema += "election_timeout_max FLOAT, " 
        schema += "max_entries_per_message int, "
        schema += "use_pre_vote BOOLEAN, "
        schema += "use_check_quorum BOOLEAN, "
        schema += "use_dynamic_config BOOLEAN) "
        cursor.execute(schema)
        schema = f"CREATE TABLE if not exists stats " \
            "(dummy INTERGER primary key, max_index INTEGER," \
            " term INTEGER, voted_for TEXT)"
        cursor.execute(schema)
        self.db.commit()
        cursor.close()
                     
    def save_entry(self, entry):
        if self.db is None: # pragma: no cover
            self.open() # pragma: no cover
        cursor = self.db.cursor()
        params = []
        values = "("
        if entry.index is not None:
            params.append(entry.index)
            sql = f"replace into records (rec_index, "
            values += "?,"
        else:
            sql = f"insert into records ("

        sql += "code, command, result, error, term, serial, leader_id, committed, applied) values "
        values += "?,?,?,?,?,?,?,?,?)"
        sql += values
        # at one time I thought this was necessary, now I don't know why
        #if isinstance(entry, RecordCode):
        #    params.append(entry.code.value)
        #else:
        #    params.append(entry.code)
        params.append(entry.code)
        params.append(entry.command)
        params.append(entry.result)
        params.append(entry.error)
        params.append(entry.term)
        if entry.serial:
            params.append(f'{entry.serial:,}')
        else:
            params.append(entry.serial)
        params.append(entry.leader_id)
        params.append(entry.committed)
        params.append(entry.applied)
        cursor.execute(sql, params)
        entry.index = cursor.lastrowid
        if cursor.lastrowid > self.max_index:
            self.max_index = cursor.lastrowid
        sql = "replace into stats (dummy, max_index, term, voted_for) values (?,?,?,?)"
        cursor.execute(sql, [1, self.max_index, self.term, self.voted_for])
        self.db.commit()
        cursor.close()
        return self.read_entry(entry.index)

    def read_entry(self, index=None):
        if self.db is None: # pragma: no cover
            self.open() # pragma: no cover
        cursor = self.db.cursor()
        if index == None:
            cursor.execute("select max(rec_index) from records")
            row = cursor.fetchone()
            index = row[0]
        sql = "select * from records where rec_index = ?"
        cursor.execute(sql, [index,])
        rec_data = cursor.fetchone()
        if rec_data is None:
            cursor.close()
            return None
        conv = dict(rec_data)
        conv['index'] = rec_data['rec_index']
        del conv['rec_index']
        if rec_data['serial']:
            conv['serial'] = int(rec_data['serial'])
        log_rec = LogRec.from_dict(conv)
        cursor.close()
        return log_rec
    
    def set_term(self, value):
        if self.db is None: # pragma: no cover
            self.open() # pragma: no cover
        cursor = self.db.cursor()
        self.term = value
        sql = "replace into stats (dummy, max_index, term, voted_for)" \
            " values (?,?,?,?)"
        cursor.execute(sql, [1, self.max_index, self.term, self.voted_for])
        self.db.commit()
        cursor.close()
    
    def set_voted_for(self, value):
        if self.db is None: # pragma: no cover
            self.open() # pragma: no cover
        cursor = self.db.cursor()
        self.voted_for = value
        sql = "replace into stats (dummy, max_index, term, voted_for)" \
            " values (?,?,?,?)"
        cursor.execute(sql, [1, self.max_index, self.term, self.voted_for])
        self.db.commit()
        cursor.close()
    
    def get_entry_at(self, index):
        if index < 1:
            return None
        return self.read_entry(index)

    def add_entry(self, rec: LogRec) -> LogRec:
        rec.index = None
        rec = self.save_entry(rec)
        return rec

    def insert_entry(self, rec: LogRec) -> LogRec:
        rec = self.save_entry(rec)
        return rec

    def get_commit_index(self):
        if self.db is None: # pragma: no cover
            self.open() # pragma: no cover
        cursor = self.db.cursor()
        sql = "select rec_index from records where committed = 1 order by rec_index desc"
        cursor.execute(sql)
        rec_data = cursor.fetchone()
        if rec_data is None:
            cursor.close()
            return 0
        cursor.close()
        return rec_data['rec_index']

    def get_applied_index(self):
        if self.db is None: # pragma: no cover
            self.open() # pragma: no cover
        cursor = self.db.cursor()
        sql = "select rec_index from records where applied = 1 order by rec_index desc"
        cursor.execute(sql)
        rec_data = cursor.fetchone()
        if rec_data is None:
            cursor.close()
            return 0
        cursor.close()
        return rec_data['rec_index']

    def delete_all_from(self, index: int):
        if self.db is None: # pragma: no cover
            self.open() # pragma: no cover
        cursor = self.db.cursor()
        cursor.execute("delete from records where rec_index >= ?", [index,])
        self.max_index = index - 1
        sql = "replace into stats (dummy, max_index, term, voted_for)" \
            " values (?,?,?,?)"
        cursor.execute(sql, [1, self.max_index, self.term, self.voted_for])
        self.db.commit()
        cursor.close()
    
    def save_cluster_config(self, config: ClusterConfig) -> None:
        if self.db is None: # pragma: no cover
            self.open() # pragma: no cover
        cursor = self.db.cursor()
        for node in config.nodes.values():
            sql = "insert or replace into nodes (uri, is_adding, is_removing, is_loading)"
            sql += " values (?,?,?,?)"
            cursor.execute(sql, [node.uri, node.is_adding, node.is_removing, node.is_loading])
        sql = "insert or replace into settings (the_index, heartbeat_period, election_timeout_min,"
        sql += "election_timeout_max, use_pre_vote, use_check_quorum, use_dynamic_config)"
        sql += " values (?,?,?,?,?,?,?)"
        cs = config.settings
        cursor.execute(sql, [1, cs.heartbeat_period, cs.election_timeout_min, cs.election_timeout_max,
                             cs.use_pre_vote, cs.use_check_quorum, cs.use_dynamic_config])
        self.db.commit()
        cursor.close()
    
    def get_cluster_config(self) -> Optional[ClusterConfig]:
        if self.db is None: # pragma: no cover
            self.open() # pragma: no cover
        cursor = self.db.cursor()
        sql = "select * from settings where the_index == 1"
        cursor.execute(sql)
        row = cursor.fetchone()
        if row is None:
            return None
        settings = ClusterSettings(heartbeat_period=row['heartbeat_period'],
                                   election_timeout_min=row['election_timeout_min'],
                                   election_timeout_max=row['election_timeout_max'],
                                   max_entries_per_message=row['max_entries_per_message'],
                                   use_pre_vote=row['use_pre_vote'],
                                   use_check_quorum=row['use_check_quorum'],
                                   use_dynamic_config=row['use_dynamic_config'])

        nodes = {}
        sql = "select * from nodes"
        cursor.execute(sql)
        for row in cursor.fetchall():
            rec = NodeRec(uri=row['uri'],
                          is_adding=row['is_adding'],
                          is_removing=row['is_removing'],
                          is_loading=row['is_loading'])
            nodes[rec.uri] = rec
        res = ClusterConfig(nodes=nodes, settings=settings)
        return res
    
class SqliteLog(LogAPI):

    def __init__(self, filepath: os.PathLike):
        self.records = None
        self.filepath = filepath
        self.logger = logging.getLogger(__name__)

    def start(self):
        # this indirection helps deal with the need to restrict
        # access to a single thread
        self.records = Records(self.filepath)
        
    def close(self):
        self.records.close()
        
    async def get_term(self) -> Union[int, None]:
        if not self.records.is_open(): # pragma: no cover
            self.records.open() # pragma: no cover
        return self.records.term
    
    async def set_term(self, value: int):
        if not self.records.is_open(): # pragma: no cover
            self.records.open() # pragma: no cover
        self.records.set_term(value)

    async def get_voted_for(self) -> Union[int, None]:
        if not self.records.is_open(): # pragma: no cover
            self.records.open() # pragma: no cover
        return self.records.voted_for
    
    async def set_voted_for(self, value: str):
        if not self.records.is_open(): # pragma: no cover
            self.records.open() # pragma: no cover
        self.records.set_voted_for(value)
        
    async def incr_term(self):
        if not self.records.is_open(): # pragma: no cover
            self.records.open() # pragma: no cover
        self.records.set_term(self.records.term + 1)
        return self.records.term

    async def append(self, entry: LogRec) -> None:
        if not self.records.is_open(): # pragma: no cover
            self.records.open() # pragma: no cover
        save_rec = LogRec.from_dict(entry.__dict__)
        return_rec = self.records.add_entry(save_rec)
        self.logger.debug("new log record %s", return_rec.index)
        return return_rec

    async def append_multi(self, entries: List[LogRec]) -> None:
        if not self.records.is_open(): # pragma: no cover
            self.records.open() # pragma: no cover
        # make copies
        return_recs = []
        for entry in entries:
            return_recs.append(await self.append(entry))
        return return_recs

    async def replace(self, entry:LogRec) -> LogRec:
        if not self.records.is_open(): # pragma: no cover
            self.records.open() # pragma: no cover
        if entry.index is None:
            raise Exception("api usage error, call append for new record")
        if entry.index < 1:
            raise Exception("api usage error, cannot insert at index less than 1")
        save_rec = LogRec.from_dict(entry.__dict__)
        next_index = self.records.max_index + 1
        if save_rec.index > next_index:
            raise Exception("cannot replace record with index greater than max record index")
        self.records.insert_entry(save_rec)
        return LogRec.from_dict(save_rec.__dict__)

    async def read(self, index: Union[int, None] = None) -> Union[LogRec, None]:
        if not self.records.is_open(): # pragma: no cover
            self.records.open() # pragma: no cover
        if index is None:
            index = self.records.max_index
        else:
            if index < 1:
                raise Exception(f"cannot get index {index}, not in records")
            if index > self.records.max_index:
                return None
        rec = self.records.get_entry_at(index)
        if rec is None:
            return None
        return LogRec.from_dict(rec.__dict__)

    async def get_last_index(self):
        if not self.records.is_open(): # pragma: no cover
            self.records.open() # pragma: no cover
        return self.records.max_index

    async def get_last_term(self):
        if not self.records.is_open(): # pragma: no cover
            self.records.open() # pragma: no cover
        rec = self.records.read_entry()
        if rec is None:
            return 0
        return rec.term

    async def update_and_commit(self, entry:LogRec) -> LogRec:
        entry.committed = True
        save_rec = self.records.insert_entry(entry)
        return save_rec
    
    async def update_and_apply(self, entry:LogRec) -> LogRec:
        entry.applied = True
        save_rec = self.records.insert_entry(entry)
        return save_rec
    
    async def get_commit_index(self):
        if not self.records.is_open(): # pragma: no cover
            self.records.open() # pragma: no cover
        return self.records.get_commit_index()

    async def get_applied_index(self):
        if not self.records.is_open(): # pragma: no cover
            self.records.open() # pragma: no cover
        return self.records.get_applied_index()

    async def delete_all_from(self, index: int):
        if not self.records.is_open(): # pragma: no cover
            self.records.open() # pragma: no cover
        return self.records.delete_all_from(index)

    async def save_cluster_config(self, config: ClusterConfig) -> None:
        return self.records.save_cluster_config(config)
    
    async def get_cluster_config(self) -> Optional[ClusterConfig]:  
        return self.records.get_cluster_config()
    
