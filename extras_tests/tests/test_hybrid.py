#!/usr/bin/env python
import asyncio
import logging
import shutil
from random import randint
from pathlib import Path
import time

import pytest
from raftengine.api.log_api import LogRec
from raftengine.api.snapshot_api import SnapShot
from raftengine.extras.hybrid_log import HybridLog
from raftengine.extras.hybrid_log.sqlite_writer import SqliteWriterControl, SqliteWriter, SqliteWriterService
from log_common import (inner_log_test_basic, inner_log_perf_run,
                    inner_log_test_deletes, inner_log_test_snapshots,
                    inner_log_test_configs
                    )
logger = logging.getLogger("test_code")

async def log_create(instance_number=0):
    path = Path('/tmp', f"test_log_{instance_number}")
    if path.exists():
        shutil.rmtree(path)
    path.mkdir()
    log = HybridLog(path)
    return log

async def log_close_and_reopen(log):
    await log.stop()
    path = Path(log.dirpath)
    log = HybridLog(path)
    return log

async def test_hybrid_basic():
    await inner_log_test_basic(log_create, log_close_and_reopen)

async def test_hybrid_deletes():
    await inner_log_test_deletes(log_create, log_close_and_reopen)

async def test_hybrid_snapshots():
    await inner_log_test_snapshots(log_create, log_close_and_reopen)

async def test_hybrid_configs():
    await inner_log_test_configs(log_create, log_close_and_reopen)

class HL(HybridLog):
       
    async def start(self):
        await self.lmdb_log.start()
        await self.sqlite_log.start()
        await self.sqlwriter.start(self.sqlwriter_callback, self.handle_writer_error, inprocess=True)
        
async def seq1(use_in_process=False):

    if use_in_process:
        path = Path('/tmp', f"test_log_1_ip")
    else:
        path = Path('/tmp', f"test_log_seq1")
    if path.exists():
        shutil.rmtree(path)
    path.mkdir()
    
    # Use controlled tuning parameters for predictable behavior
    if use_in_process:
        log = HL(path) 
    else:
        log = HybridLog(path)

    hold_count = 10
    push_trigger = 5
    copy_size = 3
    snap_size = 5
    log.set_hold_count(hold_count)
    log.set_push_trigger(push_trigger)
    await log.set_copy_size(copy_size)
    await log.set_snap_size(snap_size)
    await log.start()

    stats = await log.get_stats()
    assert stats.extra_stats.current_pressure == -hold_count
    try:
        await log.set_term(1)

        trigger_offset = hold_count + push_trigger
        needed_index = None
        async def fill_to_snap():
            # Write just enough records to trigger archiving
            # local_count - last_pressure_sent - hold_count >= push_trigger
            # Starting with last_pressure_sent = 0, we need local_count > hold_count + push_trigger = 16
            start_index = await log.get_last_index() + 1
            needed_index = start_index + trigger_offset
            #print(f"\n\nadding records from {start_index} to {needed_index}\n\n")
            for i in range(start_index, needed_index+1):
                new_rec = LogRec(index=i, command=f"add {i}", serial=i, term=1)
                rec = await log.insert(new_rec)
                if start_index == i:
                    stats = await log.get_stats()
                    # this will be state when sqlite has no records but lmdb does not
                    assert stats.record_count == 1
                #print(f"added rec {rec}")
                await log.mark_committed(i)
                await log.mark_applied(i)

            # Wait for snapshot processing to complete
            start_time = time.time()
            while time.time() - start_time < 0.5 and await log.lmdb_log.get_snapshot() is None:
                await asyncio.sleep(0.05)
                # Normally snapshots are returned when new data is sent to the sqlwriter,
                # but we may have stopped right on the boarder for that, so let's
                # use the test support mechanism for triggering snapshot delivery.
                await log.sqlwriter.send_command(dict(command="pop_snap"))

        await fill_to_snap()
        snap = await log.lmdb_log.get_snapshot() 
        assert snap is not None, "Snapshot should exist in LMDB"
        assert snap.index == snap_size, f"Snapshot index {snap.index} should be {snap_size}"

        stats = await log.get_stats()
        # this will be state when both have records
        assert stats.record_count == trigger_offset + 1 # we go one passed to cause archive snap

        # Verify that we can read a record that is prior to the snapshot, will get it from sqlite
        assert await log.read(snap.index - 1) is not None

        # Clear the log, make sure both sub logs are clear, should not have trouble due to archive snapshot
        await log.delete_all_from(1)
        assert await log.lmdb_log.get_last_index() == 0
        assert await log.lmdb_log.get_first_index() is None

        assert await log.sqlite_log.get_last_index() == 0
        assert await log.sqlite_log.get_first_index() is None

        # some additional code paths happend after start, should not change behavior
        log.set_hold_count(hold_count)
        log.set_push_trigger(push_trigger)
        await log.set_copy_size(copy_size)
        await log.set_snap_size(snap_size)
        # fill it up again
        await log.set_term(2)
        await fill_to_snap()
        snap = await log.lmdb_log.get_snapshot() 
        assert snap is not None, "Snapshot should exist in LMDB"
        
        # If we do a snapshot for the index that matches the last internal snapshot, meaning that the
        # lmdb_log already has a snapshot to sqlite that convers it, then the lmdb_log first should not
        # change
        internal_snap = await log.lmdb_log.get_snapshot()
        first_index = await log.lmdb_log.get_first_index()
        snsh = SnapShot(index=internal_snap.index, term=2)
        await log.install_snapshot(snsh)
        assert first_index == await log.lmdb_log.get_first_index()


        # install a snapshot that empties the actual records in both logs
        last_index = await log.get_last_index()
        empty_snap = SnapShot(index=last_index, term=2)
        await log.install_snapshot(empty_snap)
        assert await log.lmdb_log.get_first_index() is None
        assert await log.sqlite_log.get_first_index() is None
        assert await log.get_first_index() is None

        assert await log.lmdb_log.get_last_index() == last_index
        assert await log.sqlite_log.get_last_index()  == last_index
        assert await log.get_last_index()  == last_index
        
        # add some more
        await fill_to_snap()
        # do the special op that pushes all records into sqlite
        pre_stats =  await log.get_stats()
        await log.push_all()
        
        await asyncio.sleep(0.01)
        new_first = await log.lmdb_log.get_first_index()
        start_time = time.time()
        while time.time() - start_time < 0.5 and new_first is not None:
            await asyncio.sleep(0.01)
            new_first = await log.lmdb_log.get_first_index()
        assert new_first is None
        post_stats = await log.get_stats()

        assert pre_stats.record_count == post_stats.record_count
        assert pre_stats.first_index == post_stats.first_index
        assert pre_stats.last_index == post_stats.last_index

        # redo the push_all even though no records in log, should change nothing
        await log.push_all()
        await asyncio.sleep(0.01)
        post_stats = await log.get_stats()

        assert pre_stats.record_count == post_stats.record_count
        assert pre_stats.first_index == post_stats.first_index
        assert pre_stats.last_index == post_stats.last_index
  
    finally:
        await log.stop()

async def test_hybrid_specific():
    await seq1(use_in_process=True)
    await seq1()


async def test_enhanced_stats():
    """Test enhanced hybrid log statistics"""
    path = Path('/tmp', f"test_enhanced_stats")
    if path.exists():
        shutil.rmtree(path)
    path.mkdir()
    
    # Use controlled tuning parameters
    log = HybridLog(path, hold_count=8, push_trigger=3, push_snap_size=4, copy_block_size=2)
    await log.start()

    try:
        await log.set_term(1)
        
        # Add records to generate some statistics
        for i in range(1, 15):
            new_rec = LogRec(command=f"stats_test {i}", serial=i, term=1)
            await log.insert(new_rec)
            await log.mark_committed(i)
            await log.mark_applied(i)
            await asyncio.sleep(0.05)  # Small delay to allow processing
        
        # Wait for writer processing
        await asyncio.sleep(0.5)
        
        # Get enhanced statistics
        stats = await log.get_hybrid_stats()
        
        # Verify we got HybridStats with expected fields
        assert hasattr(stats, 'lmdb_stats'), "Should have lmdb_stats field"
        assert hasattr(stats, 'sqlite_stats'), "Should have sqlite_stats field"
        assert hasattr(stats, 'ingress_rate'), "Should have ingress_rate field"
        assert hasattr(stats, 'copy_rate'), "Should have copy_rate field"
        assert hasattr(stats, 'copy_lag'), "Should have copy_lag field"
        assert hasattr(stats, 'current_pressure'), "Should have current_pressure field"
        assert hasattr(stats, 'writer_pending_snaps_count'), "Should have writer_pending_snaps_count field"
        
        # Basic sanity checks
        assert stats.lmdb_record_count >= 0, f"LMDB record count should be non-negative: {stats.lmdb_record_count}"
        assert stats.sqlite_record_count >= 0, f"SQLite record count should be non-negative: {stats.sqlite_record_count}"
        assert stats.total_hybrid_size_bytes >= 0, f"Total size should be non-negative: {stats.total_hybrid_size_bytes}"
        
        print(f"Enhanced stats test - LMDB: {stats.lmdb_record_count}, SQLite: {stats.sqlite_record_count}")
        print(f"Copy lag: {stats.copy_lag}, Pressure: {stats.current_pressure}")
        print(f"Total size: {stats.total_hybrid_size_bytes} bytes")
        
        # Test that we have meaningful data
        assert stats.lmdb_record_count > 0, "Should have some LMDB records"
        
        print("Enhanced statistics test completed successfully!")

    finally:
        await log.stop()



class ErrorInsertLog(HybridLog):

    def __init__(self, *args, **kwargs):
        self.task_function = kwargs.pop('task_function')
        self.test_error_callback = kwargs.pop('test_error_callback', None)
        super().__init__(*args, **kwargs)
       
    async def start(self):
        await self.lmdb_log.start()
        await self.sqlite_log.start()
        self.sqlwriter = InsertableControl(self.sqlite_db_file, self.lmdb_db_path, snap_size=self.push_snap_size,
                                             copy_block_size=self.copy_block_size,
                                             task_function=self.task_function, test_error_callback=self.test_error_callback)
        await self.sqlwriter.start(self.sqlwriter_callback, self.handle_writer_error, inprocess=True)

class InsertableControl(SqliteWriterControl):
        
    def __init__(self, *args, **kwargs):
        self.task_function = kwargs.pop('task_function')
        self.test_error_callback = kwargs.pop('test_error_callback', None)
        super().__init__(*args, **kwargs)

    async def start(self, callback, error_callback, port=None, inprocess=False):
        self.callback = callback
        if self.test_error_callback:
            async def cb(error):
                try:
                    await error_callback(error)
                except:
                    traceback.format_exc()
                finally:
                    await self.test_error_callback(error)
            self.error_callback = cb
        else:
            self.error_callback = error_callback
        if port is None:
            port = randint(8000, 65000)
        self.port = port
        self.writer_task = asyncio.create_task(
            self.task_function(self.sqlite_db_path, self.lmdb_db_path, self.port, self.snap_size, self.copy_block_size)
            )
        await asyncio.sleep(0.01)
        logger.warning("sqlwriter Task started")
        self.running = True
        self.reader, self.writer = await asyncio.open_connection('localhost', self.port)
        asyncio.create_task(self.read_backchannel())
            
async def regular_writer_task(sqlite_file_path, lmdb_db_path, port, snap_size, copy_block_size):
    # This is just for testing support, having it run
    # in process helps with debugging and coverage.
    # It is not appropriate for actual use as you'll
    # lose all the benifit of the hybrid approach
    writer = SqliteWriter(sqlite_file_path, lmdb_db_path, port, snap_size, copy_block_size)
    await writer.start()
    await writer.serve()

async def break_copy_block_task(sqlite_file_path, lmdb_db_path, port, snap_size, copy_block_size):
    # This is just for testing support, having it run
    # in process helps with debugging and coverage.
    # It is not appropriate for actual use as you'll
    # lose all the benifit of the hybrid approach
    writer = BreakCopyBlock(sqlite_file_path, lmdb_db_path, port, snap_size, copy_block_size)
    await writer.start()
    await writer.serve()

class BreakCopyBlock(SqliteWriter):

    explode = True

    async def copy_block(self, first_index, last_index):
        if self.explode:
            print("\n\nRaising exception on copy block for testing\n\n")
            raise Exception("inserted error in copy_block")
        return await super().copy_block(first_index, last_index)

class InsertServiceWriter(SqliteWriter):

    def __init__(self, *args, **kwargs):
        self.service_class = kwargs.pop('service_class')
        super().__init__(*args, **kwargs)
    
    
class InsertService(SqliteWriterService):


    async def blow_up(self):
        await self.reader.close()
        await self.writer.close()

    async def handle_client(self, reader, writer):
        self.reader = reader
        self.writer = writer
        return await super().handle_client(reader, writer)
    
    
async def test_writer_errors_1():
    
    path = Path('/tmp', f"test_log_errors")
    if path.exists():
        shutil.rmtree(path)
    path.mkdir()
    log = ErrorInsertLog(path, task_function=regular_writer_task)
    hold_count = 10
    push_trigger = 5
    copy_size = 3
    snap_size = 5
    log.set_hold_count(hold_count)
    log.set_push_trigger(push_trigger)
    await log.set_copy_size(copy_size)
    await log.set_snap_size(snap_size)
    await log.start()

    await log.set_term(1)

    trigger_offset = hold_count + push_trigger
    needed_index = None
    async def fill_to_snap():
        # Write just enough records to trigger archiving
        # local_count - last_pressure_sent - hold_count >= push_trigger
        # Starting with last_pressure_sent = 0, we need local_count > hold_count + push_trigger = 16
        start_index = await log.get_last_index() + 1
        needed_index = start_index + trigger_offset
        #print(f"\n\nadding records from {start_index} to {needed_index}\n\n")
        for i in range(start_index, needed_index+1):
            new_rec = LogRec(index=i, command=f"add {i}", serial=i, term=1)
            rec = await log.insert(new_rec)
            if start_index == i:
                stats = await log.get_stats()
                # this will be state when sqlite has no records but lmdb does not
                assert stats.record_count == 1
            #print(f"added rec {rec}")
            await log.mark_committed(i)
            await log.mark_applied(i)

        # Wait for snapshot processing to complete
        start_time = time.time()
        while time.time() - start_time < 0.5 and await log.lmdb_log.get_snapshot() is None:
            await asyncio.sleep(0.05)
            # Normally snapshots are returned when new data is sent to the sqlwriter,
            # but we may have stopped right on the boarder for that, so let's
            # use the test support mechanism for triggering snapshot delivery.
            await log.sqlwriter.send_command(dict(command="pop_snap"))

    await fill_to_snap()
    snap = await log.lmdb_log.get_snapshot() 
    assert snap is not None, "Snapshot should exist in LMDB"
    assert snap.index == snap_size, f"Snapshot index {snap.index} should be {snap_size}"


    await log.stop()
    shutil.rmtree(path)
    path.mkdir()

    error_value = None
    async def error_callback(error):
        nonlocal error_value
        error_value = error

    log = ErrorInsertLog(path, task_function=break_copy_block_task, test_error_callback=error_callback)
    log.set_hold_count(hold_count)
    log.set_push_trigger(push_trigger)
    await log.set_copy_size(copy_size)
    await log.set_snap_size(snap_size)
    await log.start()
    for i in range(1, 17):
        new_rec = LogRec(index=i, command=f"add {i}", serial=i, term=1)
        rec = await log.insert(new_rec)
    start_time = time.time()
    while time.time() - start_time < 0.5 and error_value is None:
        await asyncio.sleep(0.05)

    assert error_value is not None
