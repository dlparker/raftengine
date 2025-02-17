import abc
import os
import sqlite3
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Union, List, Optional
from copy import deepcopy
import logging
from raftengine.log.log_api import LogRec, LogAPI, RecordCode

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
        schema = f"CREATE TABLE if not exists records " \
            "(rec_index INTEGER primary key, code TEXT," \
            "term INTEGER, user_data TEXT) " 
        cursor.execute(schema)
        schema = f"CREATE TABLE if not exists pending_record " \
            "(id INTEGER PRIMARY KEY AUTOINCREMENT, "\
            "rec_index INTEGER, code TEXT, " \
            "term INTEGER, user_data TEXT) " 
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

        sql += "code, term, user_data) values "
        values += "?, ?,?)"
        sql += values
        params.append(str(entry.code.value))
        params.append(entry.term)
        user_data = entry.user_data
        params.append(user_data)
        cursor.execute(sql, params)
        entry.index = cursor.lastrowid
        if cursor.lastrowid > self.max_index:
            self.max_index = cursor.lastrowid
        sql = "replace into stats (dummy, max_index, term)" \
            " values (?,?,?)"
        cursor.execute(sql, [1, self.max_index, self.term])
        self.db.commit()
        cursor.close()
        return entry

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
        user_data = rec_data['user_data']
        log_rec = LogRec(code=RecordCode(rec_data['code']),
                         index=rec_data['rec_index'],
                         term=rec_data['term'],
                         user_data=user_data)
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

    def save_pending(self, rec: LogRec) -> LogRec:
        if self.db is None:
            self.open()
        if rec.index != self.max_index + 1:
            raise Exception('new record index must match pending record index for commit')
        cursor = self.db.cursor()
        cursor.execute("select * from pending_record")
        if cursor.fetchone() != None:
            cursor.close()
            raise Exception('can only have one pending record open')
        sql = f"insert into pending_record ("
        sql += "rec_index, code, term, user_data) values "
        values = "(?,?,?,?)"
        sql += values
        params = []
        params.append(rec.index)
        params.append(str(rec.code.value))
        params.append(rec.term)
        user_data = rec.user_data
        params.append(user_data)
        cursor.execute(sql, params)
        self.db.commit()
        cursor.close()
        return rec
    
    def get_pending(self) -> LogRec:
        if self.db is None:
            self.open()
        cursor = self.db.cursor()
        cursor.execute("select * from pending_record")
        rec_data = cursor.fetchone()
        if rec_data is None:
            cursor.close()
            return None
        user_data = rec_data['user_data']
        log_rec = LogRec(code=RecordCode(rec_data['code']),
                         index=rec_data['rec_index'],
                         term=rec_data['term'],
                         user_data=user_data)
        cursor.close()
        return log_rec

    def commit_pending(self, rec: LogRec) -> LogRec:
        pending = self.get_pending()
        if not pending:
            raise Exception('no pending record exists')
        if pending.index != self.max_index + 1: 
            raise Exception('Pending record is no longer the next one for the record list, would be inconsistent if saved')
        if pending.index != rec.index:
            raise Exception('new record index must match pending record index for commit')
        # the index is correct, but our save method wants null index when inserting new record
        rec.index = None
        rec = self.save_entry(rec)
        self.clear_pending()
        return rec
        
    def clear_pending(self):
        cursor = self.db.cursor()
        cursor.execute("delete from pending_record")
        cursor.close()
        self.db.commit()
    
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

    async def append(self, entries: List[LogRec]) -> None:
        if not self.records.is_open():
            self.records.open()
        # make copies
        for entry in entries:
            save_rec = LogRec(code=entry.code,
                              index=None,
                              term=entry.term,
                              user_data=entry.user_data)
            self.records.add_entry(save_rec)
        self.logger.debug("new log record %s", save_rec.index)

    async def replace_or_append(self, entry:LogRec) -> LogRec:
        if not self.records.is_open():
            self.records.open()
        if entry.index is None:
            raise Exception("api usage error, call append for new record")
        if entry.index == 0:
            raise Exception("api usage error, cannot insert at index 0")
        save_rec = LogRec(code=entry.code,
                          index=entry.index,
                          term=entry.term,
                          user_data=entry.user_data)
        next_index = self.records.max_index + 1
        if save_rec.index == next_index:
            self.records.add_entry(save_rec)
        else:
            self.records.insert_entry(save_rec)
        return deepcopy(save_rec)

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
        return deepcopy(rec)

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

    async def save_pending(self, record: LogRec) -> None:
        self.records.save_pending(record)

    async def get_pending(self) -> LogRec:
        return self.records.get_pending()

    async def commit_pending(self, record: LogRec) -> LogRec:
        return self.records.commit_pending(record)

    async def clear_pending(self) -> LogRec:
        return self.records.clear_pending()
        
    
