import abc
import os
import sqlite3
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Union, List, Optional
import logging
from raftengine.api.log_api import LogRec, LogAPI, RecordCode

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
        else:
            self.max_index = 0
            self.term = 0
            sql = "replace into stats (dummy, max_index, term)" \
                " values (?, ?,?)"
            cursor.execute(sql, [1, self.max_index, self.term])
        
    def close(self) -> None:
        if self.db is None:
            return
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
        schema += "committed BOOLEAN)" 
        cursor.execute(schema)
        schema = f"CREATE TABLE if not exists stats " \
            "(dummy INTERGER primary key, max_index INTEGER," \
            " term INTEGER)"
        cursor.execute(schema)
        self.db.commit()
        cursor.close()
                     
    def save_entry(self, entry):
        if self.db is None:
            self.open()
        cursor = self.db.cursor()
        params = []
        values = "("
        if entry.index is not None:
            params.append(entry.index)
            sql = f"replace into records (rec_index, "
            values += "?,"
        else:
            sql = f"insert into records ("

        sql += "code, command, result, error, term, serial, leader_id, committed) values "
        values += "?,?,?,?,?,?,?,?)"
        sql += values
        if isinstance(entry, RecordCode):
            params.append(entry.code.value)
        else:
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
        cursor.execute(sql, params)
        entry.index = cursor.lastrowid
        if cursor.lastrowid > self.max_index:
            self.max_index = cursor.lastrowid
        sql = "replace into stats (dummy, max_index, term) values (?,?,?)"
        cursor.execute(sql, [1, self.max_index, self.term])
        self.db.commit()
        cursor.close()
        return self.read_entry(entry.index)

    def read_entry(self, index=None):
        if self.db is None:
            self.open()
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
        if self.db is None:
            self.open()
        cursor = self.db.cursor()
        self.term = value
        sql = "replace into stats (dummy, max_index, term)" \
            " values (?, ?,?)"
        cursor.execute(sql, [1, self.max_index, self.term])
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
        if self.db is None:
            self.open()
        cursor = self.db.cursor()
        sql = "select rec_index from records where committed = 1 order by rec_index desc"
        cursor.execute(sql)
        rec_data = cursor.fetchone()
        if rec_data is None:
            cursor.close()
            return 0
        cursor.close()
        return rec_data['rec_index']

    async def delete_all_from(self, index: int):
        if self.db is None:
            self.open()
        cursor = self.db.cursor()
        cursor.execute("delete from records where rec_index ?", [index,])
        self.db.commit()
        cursor.close()
    
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
        if not self.records.is_open():
            self.records.open()
        return self.records.term
    
    async def set_term(self, value: int):
        if not self.records.is_open():
            self.records.open()
        self.records.set_term(value)

    async def incr_term(self):
        if not self.records.is_open():
            self.records.open()
        self.records.set_term(self.records.term + 1)
        return self.records.term

    async def append(self, entry: LogRec) -> None:
        if not self.records.is_open():
            self.records.open()
        save_rec = LogRec.from_dict(entry.__dict__)
        return_rec = self.records.add_entry(save_rec)
        self.logger.debug("new log record %s", return_rec.index)
        return return_rec

    async def append_multi(self, entries: List[LogRec]) -> None:
        if not self.records.is_open():
            self.records.open()
        # make copies
        return_recs = []
        for entry in entries:
            return_recs.append(await self.append(entry))
        return return_recs

    async def replace(self, entry:LogRec) -> LogRec:
        if not self.records.is_open():
            self.records.open()
        if entry.index is None:
            raise Exception("api usage error, call append for new record")
        if entry.index == 0:
            raise Exception("api usage error, cannot insert at index 0")
        save_rec = LogRec.from_dict(entry.__dict__)
        next_index = self.records.max_index + 1
        self.records.insert_entry(save_rec)
        return LogRec.from_dict(save_rec.__dict__)

    async def read(self, index: Union[int, None] = None) -> Union[LogRec, None]:
        if not self.records.is_open():
            self.records.open()
        if index is None:
            index = self.records.max_index
        else:
            if index < 1:
                raise Exception(f"cannot get index {index}, not in records")
            if index > self.records.max_index:
                raise Exception(f"cannot get index {index}, not in records")
        rec = self.records.get_entry_at(index)
        if rec is None:
            return None
        return LogRec.from_dict(rec.__dict__)

    async def get_last_index(self):
        if not self.records.is_open():
            self.records.open()
        return self.records.max_index

    async def get_last_term(self):
        if not self.records.is_open():
            self.records.open()
        rec = self.records.read_entry()
        if rec is None:
            return 0
        return rec.term

    async def update_and_commit(self, entry:LogRec) -> LogRec:
        entry.committed = True
        save_rec = self.records.insert_entry(entry)
        return save_rec
    
    async def get_commit_index(self):
        if not self.records.is_open():
            self.records.open()
        return self.records.get_commit_index()

    async def delete_all_from(self, index: int):
        if not self.records.is_open():
            self.records.open()
        return self.records.delete_all_from(index)
    
