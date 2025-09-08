"""
Theory of ops for using Sqlite as an automatic prune assistant for LMDB primary store by
using the Sqlite log as an online, live archive of the primary store. These mechanisms
are the exact, unmodified versions of the Raftengine LogAPI compliant components that
can be used directly.

Notes:
1. The purpose of this design is to reduce the chance that you will run out of space for
   the lmdb records and to do that at a slight performance cost on a fully loaded system.
2. It is unlikely to have the desired effect if a system is loaded to the maximum possible
   record generation rate for its entire service life, as the sqlite store will never catch up.
3. For best results it may need tuning so various dials and knobs are provided.

The incomming records are written to LMDB log immediately. When certain threasholds
are met the SqliteWriter begins copying record to the sqlite log. The LMDB operations
take place in the main process, and the SqliteWriter operations take place in a
child process. Under certain conditions the LMDB side sends a record index as a "limit"
to the SqliteWriter. The SqliteWriter examines its own records and determines
the gap between the its own max index and the sent limit and copies the records from LMDB
log to Sqlite log. It does this with as many loops as needed in order to catch up the
the current limit value, where each loop handles copy_block_size records, max. Each
pass of the loop opens a closes and reopens the LMDB log connection. Although it
is technically feasable to rely on transaction control to interleave this with writes
from the main process, testing has demonstrated that stale reads are common, possibly
because of some specific aspect of the LMDB log code's management of the LMDB store.

Periodically, the SqlWriter process sends a SnapShot to the main process. This is just
like a Raftenine SnapShot record, with the index and the term being those of the targeted
record. This informs the main process that it should install the snapshot, which leads
to pruning the records from the beginning of the LMDB log up to the snapshot index. 
The rate of snapshot operations is a tunable parameter meant to ensure that the main process
does not spend too much time in the record delete operation, which has to be done one at a
time in LMDB. There is a queue of uninstalled snapshots in memory in the LMDB side
to avoid missing things on overlap and to provide an opportunity to throttle the delete operations.

When the user code (actually either the Leader or Follower class) requests a read operation
the HybridLog read code checks to see which log contains the record and routes the request
there. Most other LogAPI operations are performed by simply calling the LDMB log. There are
some exceptions. The install_snapshot and get_snapshot calls are seriviced using the sqlite
log. There is some complexity here when a snapshot index value is in the LMDB log instead
of sqlite: it always installs to Sqlite first, then conditionally to LMDB only if the new
snapshot advances beyond the existing LMDB snapshot. 

The sqlitewriter makes no adjustments to the rate at which it works, it simply copies records until it
catches up to the push limit, a number that will keep growing until it has caught up. Catching up will
only happen if the rate of incomming messages in the lmdb side drops below the maximum rate of the sqlite
side, plus a bit for extra operations. In my testing in a raft environment a typical ratio of rates is
lmdb did about 3800 records per second and sqlite did about 2100. 

Communications between the two is by async socket calls so that both sides can handle the comms
in a fully async fashion. Python multiprocessing is nice to use except for the fact that the
interprocess communications apis are all synchronous, so using them from async code requires methods
that waste time an impact performance near full system load.

The timing of these archiving operations are controlled by these parameters:

1. hold_count - This is the number of records that the LDMB log should retain and not
   send to archive.
2. push_trigger -  This is combined with the calculate value for "pressure" to decide
   when to send a new limit message to the SqliteWriter process.
3. pressure - calculated fron the number of records in LMDB, the hold_count value, and
   the history of the last value of limit sent to the SqliteWriter
4. push_snap_size - This is controls the counter used by the SqliteWriter to decide when
   to send a snapshot to the main process.
5. copy_block_size - This is controls the number of copy operations that the SqliteWriter
   copy loop completes within a single transaction.

"""
import asyncio
import time
import sys
from dataclasses import dataclass, field, asdict
from typing import Union, List, Optional
import logging
from dataclasses import dataclass, asdict
from multiprocessing import Manager, Process, Queue
import queue
import traceback
from pathlib import Path
from copy import deepcopy
from raftengine.api.log_api import LogRec, LogAPI, LogStats
from raftengine.api.snapshot_api import SnapShot
from raftengine.api.types import ClusterConfig, NodeRec, ClusterSettings

from raftengine.extras.sqlite_log import SqliteLog
from raftengine.extras.lmdb_log import LmdbLog
from .sqlite_writer import SqliteWriterControl

logger = logging.getLogger('HybridLog')


@dataclass
class HybridStats:
    """Enhanced statistics for hybrid log with data-driven tuning metrics"""
    # Base stats from LMDB and Sqlite (composed)
    lmdb_stats: LogStats
    sqlite_stats: LogStats
    
    # Hybrid-specific metrics
    ingress_rate: float  # LMDB records_per_minute
    copy_rate: float     # Sqlite records_per_minute during copies
    copy_lag: int        # LMDB last_index - Sqlite last_index
    lmdb_record_count: int
    sqlite_record_count: int
    current_pressure: int        # Calculated pressure value
    last_limit_sent: int         # self.last_pressure_sent
    lmdb_percent_remaining: float
    total_hybrid_size_bytes: int
    
    # Writer-side metrics (from SqliteWriter)
    current_copy_limit: int
    upstream_commit_lag: int
    upstream_apply_lag: int
    copy_blocks_per_minute: float
    


LMDB_MAP_SIZE=10**9 * 2

class HybridLog(LogAPI):
    
    def __init__(self, dirpath, hold_count=100000, push_trigger=50, push_snap_size=100, copy_block_size=50):
        self.dirpath = dirpath 
        self.hold_count = hold_count
        self.last_pressure_sent = 0
        self.push_trigger = push_trigger
        self.push_snap_size = push_snap_size
        self.copy_block_size = copy_block_size
        self.sqlite_db_file = Path(dirpath, 'hybrid_log.db')
        self.sqlite_log = SqliteLog(self.sqlite_db_file, enable_wal=True)
        self.lmdb_db_path = Path(dirpath, 'hybrid_log.lmdb')
        self.lmdb_log = LmdbLog(self.lmdb_db_path, map_size=LMDB_MAP_SIZE)
        self.last_lmdb_snap = None # this will be snapshot to sqlite, not "real" one
        self.sw_control = SqliteWriterControl(self.sqlite_db_file, self.lmdb_db_path, snap_size=self.push_snap_size,
                                             copy_block_size=self.copy_block_size)
        self.running = True
        self.writer_stats = {}  # Storage for writer stats
        self.stats_request_event = None  # Event for async stats collection
        self.fatal_error = None

    def set_hold_count(self, value):
        self.hold_count = value

    def set_push_trigger(self, value):
        self.push_trigger = value

    async def set_copy_size(self, value):
        self.copy_block_size = value
        await self.sw_control.set_copy_block_size(value)

    async def set_snap_size(self, value):
        self.push_snap_size = value
        await self.sw_control.set_snap_size(value)
        
    # BEGIN API METHODS
    #API Method
    async def start(self):
        await self.lmdb_log.start()
        await self.sqlite_log.start()
        await self.sw_control.start(self.sw_control_callback, self.handle_writer_error)
        self.running = True
        
    #API Method
    async def stop(self):
        self.running = False
        if self.lmdb_log:
            await self.lmdb_log.stop()
            self.lmdb_log = None
        if self.sqlite_log:
            await self.sqlite_log.stop()
            self.sqlite_log = None
        if self.sw_control:
            await self.sw_control.stop()
            self.sw_control = None
            
    #API Method
    async def get_broken(self) -> bool:
        return  await self.sqlite_log.get_broken() or await self.lmdb_log.get_broken()
    
    #API Method
    async def set_broken(self) -> None:
        await self.sqlite_log.set_broken()
        return await self.lmdb_log.set_broken()
    
    #API Method
    async def set_fixed(self) -> None:
        await self.sqlite_log.set_fixed()
        return await self.lmdb_log.set_fixed()

    #API Method
    async def get_uri(self) -> Union[str, None]:
        return await self.lmdb_log.get_uri()
    
    #API Method
    async def set_uri(self, uri: str):
        await self.lmdb_log.set_uri(uri)

    #API Method
    async def get_term(self) -> Union[int, None]:
        return await self.lmdb_log.get_term()
    
    #API Method
    async def set_term(self, value: int):
        await self.sqlite_log.set_term(value)
        return await self.lmdb_log.set_term(value)

    #API Method
    async def incr_term(self):
        return await self.set_term(await self.get_term() + 1)

    #API Method
    async def get_voted_for(self) -> Union[str, None]:
        return await self.lmdb_log.get_voted_for()
    
    #API Method
    async def set_voted_for(self, value: str):
        await self.sqlite_log.set_voted_for(value)
        return await self.lmdb_log.set_voted_for(value)

    #API Method
    async def get_last_index(self):
        return await self.lmdb_log.get_last_index()

    #API Method
    async def get_first_index(self):
        lfirst = await self.lmdb_log.get_first_index()
        if lfirst is None:
            return await self.sqlite_log.get_first_index()
        return lfirst
    
    #API Method
    async def get_last_term(self):
        return await self.lmdb_log.get_last_term()
    
    #API Method
    async def get_commit_index(self):
        return await self.lmdb_log.get_commit_index()

    #API Method
    async def get_applied_index(self):
        return await self.lmdb_log.get_applied_index()
        
    #API Method
    async def insert(self, record: LogRec) -> None:
        async def relieve_pressure(new_limit):
            await self.sw_control.send_limit(new_limit,
                                            await self.lmdb_log.get_commit_index(),
                                            await self.lmdb_log.get_applied_index())
            self.last_pressure_sent = new_limit
            logger.debug("Sent limit %d to sqlite_writer, last_pressue now equals new_limit", new_limit)
        rec = await self.lmdb_log.insert(record)
        last = await self.lmdb_log.get_last_index()
        first = await self.lmdb_log.get_first_index() 
        local_count = last - first
        # The last_pressure_sent value is either is or will become
        # the first index. So if we have enough records in local
        # store, taking this into account, to exceed the number
        # we are supposed to retain, then do a signal to
        # SqliteWriter. The number to signal is a record index
        # to be the copy_stop value. That will be the current
        # last index (from the new record) minus the hold count.
        current_pressure = local_count - self.last_pressure_sent - self.hold_count
        if current_pressure >= self.push_trigger:
            new_limit = rec.index - self.hold_count
            asyncio.create_task(relieve_pressure(new_limit))
        await asyncio.sleep(0.0)
        return rec

    #API Method
    async def mark_committed(self, index:int) -> None:
        return await self.lmdb_log.mark_committed(index)

    #API Method
    async def mark_applied(self, index:int) -> None:
        return await self.lmdb_log.mark_applied(index)
    
    #API Method
    async def read(self, index: Union[int, None] = None) -> Union[LogRec, None]:
        if index is None:
            return await self.lmdb_log.read(index)
        elif self.last_lmdb_snap and self.last_lmdb_snap.index >= index:
            return await self.sqlite_log.read(index)
        return await self.lmdb_log.read(index)
    
    #API Method
    async def delete_all_from(self, index: int):
        snapshot = await self.sqlite_log.get_snapshot()
        if snapshot and index < snapshot.index + 1:
            raise Exception(f"cannot delete record {index}, snapshot happened after record stored")
        s_first = await self.sqlite_log.get_first_index()
        if s_first is not None:
            s_last = await self.sqlite_log.get_last_index()
            if index < s_last:
                await self.sqlite_log.delete_all_from(index)
                await self.sw_control.send_note_delete(index - 1)
        if index == 1:
            self.last_pressure_sent = 0
        else:
            self.last_pressure_sent = min(index, self.last_pressure_sent)
        # if it didn't blow up from a sqlite snapshot, then make sure our lmdb snapshot
        # does't interfere cause it isn't 'real'
        lm_snap = await self.lmdb_log.get_snapshot()
        if not lm_snap or lm_snap.index < index:
            # all okay, just call delete
            await self.lmdb_log.delete_all_from(index)
            return
        # our delete index looks like it is in the
        # snapshot on lmdb log, so we can't delete
        # from there, so clear everything
        await self.lmdb_log.clear_despite_snapshot()
        return

    #API Method
    async def save_cluster_config(self, config: ClusterConfig) -> None:
        await self.sqlite_log.save_cluster_config(config)
        return await self.lmdb_log.save_cluster_config(config)
    
    #API Method
    async def get_cluster_config(self):
        return await self.lmdb_log.get_cluster_config()
    
    #API Method
    async def install_snapshot(self, snapshot:SnapShot):
        await self.sqlite_log.refresh_stats()
        max_index = await self.lmdb_log.get_last_index()
        if snapshot.index > max_index or snapshot.index == 0:
            raise Exception(f"Cannot install snapshot at index={snapshot.index}, last record index is {max_index}")
        
        await self.sqlite_log.special_install_snapshot(snapshot)
        lm_snap = await self.lmdb_log.get_snapshot()
        if lm_snap and lm_snap.index >= snapshot.index:
            # sqlite write snapshot already cleared records
            # at or past the end of the new "real" snapshot,
            # so lmdb does not change
            return snapshot
        lmdb_first = await self.lmdb_log.get_first_index()
        lmdb_last = await self.lmdb_log.get_last_index()
        if lmdb_first and snapshot.index > lmdb_first:
            await self.lmdb_log.install_snapshot(snapshot)
        return snapshot
            
    #API Method
    async def get_snapshot(self):
        # always get it from sqlite, that way we can use
        # the one in lmdb to track snapshost to sqlite
        # instead of "real" snapshots
        return await self.sqlite_log.get_snapshot()

    #API Method
    async def get_stats(self) -> LogStats:
        lmdb_stats = await self.lmdb_log.get_stats()
        sqlite_stats = await self.sqlite_log.get_stats()

        # figure out how many are in lmdb but not sqlite, this is the overlap
        lmdb_last = await self.lmdb_log.get_last_index()
        lmdb_first = await self.lmdb_log.get_first_index()
        sqlite_last = await self.sqlite_log.get_last_index()
        sqlite_first = await self.sqlite_log.get_first_index()
        last_index = lmdb_last
        if sqlite_first is None and lmdb_first is None:
            # all empty or just after snapshot
            record_count = 0
            first_index = None
        elif lmdb_first is None:
            # sqlite has records (first test failed) but lmdb does not
            # unlikely in practice, but possible
            record_count = sqlite_stats.record_count
            first_index = sqlite_first
        elif sqlite_first is None:
            # lmdb has records but sqlite doesn't
            record_count = lmdb_stats.record_count
            first_index = lmdb_first
        else:
            # both have records
            record_count = lmdb_last - sqlite_first + 1
            first_index = sqlite_first
        snap_index = None
        snapshot = await self.sqlite_log.get_snapshot()
        if snapshot:
            snap_index = snapshot.index
        if snap_index is not None:
            records_since = lmdb_last - snap_index 
        else:
            records_since = record_count
        return LogStats(
            first_index=first_index,
            last_index=last_index, 
            last_term=await self.lmdb_log.get_last_term(),
            record_count=record_count, 
            records_since_snapshot=records_since,
            records_per_minute=lmdb_stats.records_per_minute,
            percent_remaining=None,  # SQLite has unlimited storage
            total_size_bytes=lmdb_stats.total_size_bytes + sqlite_stats.total_size_bytes,
            snapshot_index=snap_index,
            last_record_timestamp=lmdb_stats.last_record_timestamp,
            extra_stats=await self.get_hybrid_stats()
        )

    async def push_all(self):
        # Force all the current records to sqlite. This has value for testing,
        # and it may have value for adminstrative purposes. For example, you
        # could stop a server, open the log and push, close the log, then make
        # a copy of the sqlite log for offline analysis of activity.
        last_index = await self.lmdb_log.get_last_index()
        await self.sw_control.send_hard_push(last_index,
                                            await self.lmdb_log.get_commit_index(),
                                            await self.lmdb_log.get_applied_index())
        
        
    async def get_writer_stats(self) -> dict:
        """Get stats from writer process via socket"""
        self.stats_request_event = asyncio.Event()
        await self.sw_control.send_command({'command': 'get_stats'})
        
        # Wait for response with timeout
        try:
            await asyncio.wait_for(self.stats_request_event.wait(), timeout=0.1)
            return self.writer_stats.copy()
        finally:
            self.stats_request_event = None
    
    async def get_hybrid_stats(self) -> HybridStats:
        """Get comprehensive hybrid log statistics"""
        # Get base stats from both logs
        lmdb_stats = await self.lmdb_log.get_stats()
        sqlite_stats = await self.sqlite_log.get_stats()
        
        # Calculate hybrid-specific metrics
        lmdb_last = await self.lmdb_log.get_last_index()
        sqlite_last = await self.sqlite_log.get_last_index()
        
        # Get writer stats via socket command
        writer_stats = await self.get_writer_stats()
        
        # Calculate pressure
        current_pressure = await self._calculate_pressure()
        
        return HybridStats(
            lmdb_stats=lmdb_stats,
            sqlite_stats=sqlite_stats,
            ingress_rate=lmdb_stats.records_per_minute,
            copy_rate=sqlite_stats.records_per_minute,
            copy_lag=lmdb_last - sqlite_last,
            lmdb_record_count=lmdb_stats.record_count,
            sqlite_record_count=sqlite_stats.record_count,
            current_pressure=current_pressure,
            last_limit_sent=self.last_pressure_sent,
            lmdb_percent_remaining=lmdb_stats.percent_remaining,
            total_hybrid_size_bytes=lmdb_stats.total_size_bytes + sqlite_stats.total_size_bytes,
            current_copy_limit=writer_stats['current_copy_limit'],
            upstream_commit_lag=writer_stats['upstream_commit_lag'],
            upstream_apply_lag=writer_stats['upstream_apply_lag'],
            copy_blocks_per_minute=writer_stats['copy_blocks_per_minute']
        )

    async def sw_control_callback(self, code, data):
        async def process_snapshot(curr_snapshot):
            try:
                await self.sqlite_log.refresh_stats()
                last_index = await self.lmdb_log.get_last_index()
                first_index = await self.lmdb_log.get_first_index()
                logger.debug(f"before installing sqlite snapshot {curr_snapshot}, " \
                             f"lmdb_last_index = {last_index}, lmdb_first_index = {first_index}")
                await self.lmdb_log.install_snapshot(curr_snapshot)
                last_index = await self.lmdb_log.get_last_index()
                first_index = await self.lmdb_log.get_first_index()
                logger.debug(f"after installing sqlite snap {curr_snapshot}, "\
                             f"lmdb_last_index = {last_index}, lmdb_first_index = {first_index}")
                self.last_lmdb_snap = curr_snapshot
            except:
                logger.error(f"sqlwriter snapshot {curr_snapshot} caused error {traceback.format_exc()}")
                await self.stop()
                raise
        if code == "snapshot":
            logger.debug("got sqlitewriter snapshot %s", str(data))
            await process_snapshot(data)
        elif code == "stats":
            self.writer_stats = data
            logger.debug("got sqlitewriter stats %s", data)
            if self.stats_request_event:
                self.stats_request_event.set()
        else:
            logger.error("got unknown code from sqlitewriter %s", code)
            await self.stop()
            raise Exception(f"got unknown code from sqlitewriter {code}")
    async def handle_writer_error(self, error):
        logger.error(f"sqlwriter got error {error}")
        self.fatal_error = error
        await self.set_broken()
        
    async def _calculate_pressure(self) -> int:
        """Calculate current pressure value for tuning analysis"""
        last = await self.lmdb_log.get_last_index()
        first = await self.lmdb_log.get_first_index()
        if first is None:
            first = 0
        local_count = last - first
        # Replicate the logic from append() method
        current_pressure = local_count - self.last_pressure_sent - self.hold_count
        return current_pressure

