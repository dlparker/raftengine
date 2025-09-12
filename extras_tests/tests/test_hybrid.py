#!/usr/bin/env python
import asyncio
import logging
import shutil
import traceback
import types
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
        await self.sw_control.start(self.sw_control_callback, self.handle_writer_error, inprocess=True)
        
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


class InsertableControl(SqliteWriterControl):
    # Replaces SqliteWriterControl when wired up properly, allowing specific
    # error insertion tools to be configured via the extra "task_function" and
    # "test_error_callback" args. The task_function argument replaces
    # the real code's use of the "writer_task" function for in_process SqliteWriter
    # an SqliteWriterService operations. In this way it becomes possible to
    # configure patched versions of those classes that do error insertion for testing.
        
    def __init__(self, *args, **kwargs):
        self.task_function = kwargs.pop('task_function')
        self.test_error_callback = kwargs.pop('test_error_callback', None)
        super().__init__(*args, **kwargs)
        self.step_to_break = None
        self.break_exception = None
        self.sim_request = None
        self.handle_exit_callback = None

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
        reader, self.writer = await asyncio.open_connection('localhost', self.port)
        self.real_reader = reader
        self.reader = StreamReaderWrapper(reader)
        asyncio.create_task(self.read_backchannel())

    async def get_message(self):
        # when we are running test code and trying to set up
        # to mess with the return value, the call to read
        # has already been made by SqliteWriterControl.read_backchannel()
        # so we have to catch it on the way out.
        if self.step_to_break == "get_message":
            if self.break_exception:
                raise self.break_exception
            else:
                return None
        elif self.sim_request:
            data = self.sim_request
            self.sim_request = None
            return data
        logger.debug(f"get_message wrapper calling super")
        real_res = await super().get_message()
        return real_res

    async def read_backchannel(self):
        res = await super().read_backchannel()
        if self.handle_exit_callback:
            await self.handle_exit_callback(res)
            self.handle_exit_callback = None
        return res
        
class ErrorInsertLog(HybridLog):
    # Adds support for wiring InsertableControl in to replaces SqliteWriterControl.
    # Passes "task_function" and "test_error_callback" arguments through to
    # InsertableControl

    def __init__(self, *args, **kwargs):
        self.task_function = kwargs.pop('task_function')
        self.test_error_callback = kwargs.pop('test_error_callback', None)
        super().__init__(*args, **kwargs)
       
    async def start(self):
        await self.lmdb_log.start()
        await self.sqlite_log.start()
        self.sw_control = InsertableControl(self.sqlite_db_file, self.lmdb_db_path, snap_size=self.push_snap_size,
                                             copy_block_size=self.copy_block_size,
                                             task_function=self.task_function, test_error_callback=self.test_error_callback)
        await self.sw_control.start(self.sw_control_callback, self.handle_writer_error, inprocess=True)


sqlite_writer_in_use = None

async def regular_writer_task(sqlite_file_path, lmdb_db_path, port, snap_size, copy_block_size):
    # This is a direct replacement for the writer_task function in sqlite_writer.py, just
    # makes it possible to get at the writer class. It is wired up by using
    # ErrorInsertLog and passing "task_function=reqular_writer_task"
    writer = SqliteWriter(sqlite_file_path, lmdb_db_path, port, snap_size, copy_block_size)
    global sqlite_writer_in_use
    sqlite_writer_in_use = writer
    await writer.start()
    await writer.serve()

class BreakCopyBlockWriter(SqliteWriter):
    # arranges to raise an exception in the copy_block method of SqliteWriter if explode == True
    
    explode = True

    async def copy_block(self, first_index, last_index):
        if self.explode:
            print("\n\nRaising exception on copy block for testing\n\n")
            raise Exception("inserted error in copy_block")
        return await super().copy_block(first_index, last_index)

async def break_copy_block_task(sqlite_file_path, lmdb_db_path, port, snap_size, copy_block_size):
    # Configures copy block breaker. It is wired up by using
    # ErrorInsertLog and passing "task_function=break_copy_block_task"
    writer = BreakCopyBlockWriter(sqlite_file_path, lmdb_db_path, port, snap_size, copy_block_size)
    global sqlite_writer_in_use
    sqlite_writer_in_use = writer
    await writer.start()
    await writer.serve()


async def test_writer_errors_1():

    path = Path('/tmp', f"test_log_errors")
    if path.exists():
        shutil.rmtree(path)
    path.mkdir()

    # The first part here is mainly just to ensure that the testing tools, wrappers, replacements, etc
    # do not unintentionally break the functions under test.

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

    await fill_to_snap()
    snap = await log.lmdb_log.get_snapshot() 
    assert snap is not None, "Snapshot should exist in LMDB"
    assert snap.index == snap_size, f"Snapshot index {snap.index} should be {snap_size}"

    await log.stop()
    shutil.rmtree(path)
    path.mkdir()

    # Now we want to repeat the log insert process so that we trigger copy_block as we did
    # above, but now we do it with stuff wired up to cause the copy_block function to get
    # and error.
    
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
    assert "error in copy_block" in error_value

    # now make the copy blow up in push all
    log = ErrorInsertLog(path, task_function=break_copy_block_task, test_error_callback=error_callback)
    log.set_hold_count(hold_count)
    log.set_push_trigger(push_trigger)
    await log.set_copy_size(copy_size)
    await log.set_snap_size(snap_size)
    await log.start()
    for i in range(1, 3):
        new_rec = LogRec(index=i, command=f"add {i}", serial=i, term=1)
        rec = await log.insert(new_rec)


    await log.push_all()
    start_time = time.time()
    while time.time() - start_time < 0.5 and error_value is None:
        await asyncio.sleep(0.05)
    assert error_value is not None
    assert "error in copy_block" in error_value

    
class InsertServiceWriter(SqliteWriter):

    def __init__(self, *args, **kwargs):
        self.service_class = kwargs.pop('service_class')
        super().__init__(*args, **kwargs)
        self.writer_service = self.service_class(self, port=self.port)
        self.hang_copy_task = False

    async def copy_task(self):
        save_handle = self.copy_task_handle
        await super().copy_task()
        if not self.hang_copy_task:
            return
        self.copy_task_handle = save_handle
        try:
            while self.copy_task_handle:
                await asyncio.sleep(0.01)
        except asyncio.CancelledError as e:
            self.hang_copy_task = False
            raise
        self.copy_task_handle = None
        
        
class StreamReaderWrapper:

    def __init__(self, real):
        self.real = real
        self.read_no_length = False
        self.read_no_message = False
        self.explode_on_length = False
        self.have_length = False
        
    async def read(self, length):
        try:
            res = await self.real.read(length)
            if length == 20 and not self.have_length:
                if self.read_no_length:
                    logger.debug(f"Wrapper returning None on length read")
                    return None
                if self.explode_on_length:
                    raise Exception('Exploding in inserted error reading length from command channel')
                self.have_length = True
                logger.debug(f"Wrapper returning from length read with {res}")
            else:
                self.have_length = False
                if self.read_no_message:
                    logger.debug(f"Wrapper returning None on message read length {length}")
                    return None
        except:
            res = None
            logger.debug(traceback.format_exc())
            raise
        logger.debug(f"Read of length {length} got res={res}")
        return res
        
class StreamWriterWrapper:

    def __init__(self, real):
        self.real = real
        self.explode_on_send = False

    def get_extra_info(self, *args, **kwargs):
        return self.real.get_extra_info(*args, **kwargs)
    
    def write(self, data):
        if self.explode_on_send:
            raise Exception('Exploding on inserted error in stream send')
        return self.real.write(data)

    def drain(self):
        return self.real.drain()
    
class InsertService(SqliteWriterService):
    # this class allows error insertion in the SqliteWriterService operations
    # Set it up like this:
    #    sql_writer = InsertService
    #    log = ErrorInsertLog(path, task_function=insert_service_task)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.step_to_break = None
        self.break_exception = None
        self.handle_exit_callback = None
        self.explode_on_stop = False
        self.explode_on_sock_close = False
        self.sim_request = None
        self.real_reader = None
        self.real_writer = None

    async def stop(self):
        if self.explode_on_stop:
            if self.explode_on_sock_close:
                class ssss:
                    def close(self):
                        raise Exception("Exception: inserted error on sock_server close")
                self.sock_server = ssss()
            raise Exception('Exception: inserted error on stop')
        return await super().stop()

    async def get_request(self):
        # when we are running test code and trying to set up
        # to mess with the return value, the call to read
        # has already been made by SqliteWriterService.handle_client
        # so we have to catch it on the way out.
        if self.step_to_break == "get_request":
            if self.break_exception:
                raise self.break_exception
            else:
                return None
        elif self.sim_request:
            data = self.sim_request
            self.sim_request = None
            return data
        logger.debug(f"get_request wrapper calling super")
        real_res = await super().get_request()
        return real_res
    
    async def handle_client(self, reader, writer):
        self.real_reader = reader
        reader_wrapper = StreamReaderWrapper(reader)
        self.real_writer = writer
        writer_wrapper = StreamWriterWrapper(writer)
        res = await super().handle_client(reader_wrapper, writer_wrapper)
        if self.handle_exit_callback:
            await self.handle_exit_callback(res)
            self.handle_exit_callback = None
        return res

    async def report_fatal_error(self, msg):
        if self.handle_exit_callback:
            await self.handle_exit_callback(msg)
            self.handle_exit_callback = None
        return await super().report_fatal_error(msg) 

        
async def insert_service_task(sqlite_file_path, lmdb_db_path, port, snap_size, copy_block_size):
    # Configures error insert writer and service. It is wired up by using
    # ErrorInsertLog and passing "task_function=insert_service_task"

    writer = InsertServiceWriter(sqlite_file_path, lmdb_db_path, port, snap_size, copy_block_size,
                                 service_class=InsertService)
    global sqlite_writer_in_use
    sqlite_writer_in_use = writer
    await writer.start()
    await writer.serve()

async def errors_2_log_setup():

    # Sets up the scafolding and wrappers for a number of error tests
    # by creating a log instance that is wrapped to for error insertion,
    # with touchpoints by using InsertServiceWriter and InsertService
    # wrappers for SqliteWriter and SqliteWriterService
    
    path = Path('/tmp', f"test_log_errors")
    if path.exists():
        shutil.rmtree(path)
    path.mkdir()

    sql_writer = InsertService
    log = ErrorInsertLog(path, task_function=insert_service_task)
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
    global sqlite_writer_in_use
    assert isinstance(sqlite_writer_in_use, InsertServiceWriter)
    assert isinstance(sqlite_writer_in_use.writer_service, InsertService)
    return log

async def test_writer_errors_2():
    
    exit_reason = None
    async def cb(reason):
        nonlocal exit_reason
        exit_reason = reason

    # make SqliteWriterService experience errors in the main read loop by rasing
    # exceptions in the wrapper for get_request()

    for exc in (asyncio.CancelledError('Cancel'), ConnectionResetError('Reset'), Exception('Exc')):
        log = await errors_2_log_setup()

        service = sqlite_writer_in_use.writer_service
        service.step_to_break = "get_request"
        service.break_exception = exc
        service.handle_exit_callback = cb
        exit_reason = None
        try:
            await log.get_stats()
        except:
            pass
        start_time = time.time()
        while exit_reason is None and time.time() - start_time < 0.5:
            await asyncio.sleep(0.001)
        if "Exc" == str(exc):
            assert "Exception: Exc" in exit_reason
        else:
            assert exit_reason == exc


    # Make get_request() wrapper return None, which looks like socket closed.
    # Not an error, but follows some of the same path, this catches the differences.

    log = await errors_2_log_setup()
    service = sqlite_writer_in_use.writer_service
    service.step_to_break = "get_request"
    service.break_exception = None
    service.handle_exit_callback = cb
    exit_reason = None
    
    await log.get_stats()
    assert "socket_closed" in exit_reason

    # Make get_request() wrapper return  a quit command.
    # Not an error, but follows some of the same path, this catches the differences.
    
    log = await errors_2_log_setup()
    service = sqlite_writer_in_use.writer_service
    service.sim_request = dict(command="quit")
    service.break_exception = None
    service.handle_exit_callback = cb
    exit_reason = None
    await log.get_stats()

    start_time = time.time()
    while exit_reason is None and time.time() - start_time < 0.5:
        await asyncio.sleep(0.001)
    assert "on_request" in exit_reason

async def test_writer_errors_3():
    
    exit_reason = None
    async def cb(reason):
        nonlocal exit_reason
        exit_reason = reason

    # Arrage to have get_request receive a None instead of a length from reader.read(20)
    logger.info("checking command channel length not present")
    
    log = await errors_2_log_setup()
    service = sqlite_writer_in_use.writer_service
    wrapper = service.reader 
    wrapper.read_no_length = True
    service.handle_exit_callback = cb
    exit_reason = None
    with pytest.raises(asyncio.TimeoutError) as excinfo:
        await log.get_stats()
    assert "socket_close" in exit_reason

    # Arrage to have get_request receive a None instead of a the message it expects after reading the length
    logger.info("checking command channel length present but no message")
    log = await errors_2_log_setup()
    service = sqlite_writer_in_use.writer_service
    wrapper = service.reader 
    wrapper.read_no_message = True
    service.handle_exit_callback = cb
    exit_reason = None
    with pytest.raises(asyncio.TimeoutError) as excinfo:
        await log.get_stats()
    assert "socket_close" in exit_reason

async def test_writer_errors_4():

    exit_reason = None
    async def cb(reason):
        nonlocal exit_reason
        exit_reason = reason
    
    # When an exception is raised in get_request, SqliteWriterService.report_fatal_error should
    # be called. It is supposed to send a message on the back channel reporting the error, but
    # that could get an error. Here we simulate that situation and check that the related error handling
    # logic does it's thing
    logger.info("checking send error on fatal report")
    
    log = await errors_2_log_setup()
    service = sqlite_writer_in_use.writer_service
    reader_wrapper = service.reader 
    reader_wrapper.explode_on_length = True
    writer_wrapper = service.writer 
    writer_wrapper.explode_on_send = True
    service.explode_on_stop = True
    service.explode_on_sock_close = True
    service.handle_exit_callback = cb
    exit_reason = None
    with pytest.raises(asyncio.TimeoutError) as excinfo:
        await log.get_stats()

    assert "inserted error" in exit_reason
    assert "reading length" in  exit_reason
    #print(f"\n\n-------------------------------\n\n{service.fatal_error}\n---------------------------\n\n")
    assert "inserted error in stream send" in service.fatal_error
    assert "inserted error on stop" in service.fatal_error
    assert "inserted error on sock_server close" in service.fatal_error

async def test_writer_copy_task():

    # We want to fire off the copy_task but modify it to enter a wait loop
    # instead of exiting then ensure that it the stop sequence actually stops it.

    log = await errors_2_log_setup()
    service = sqlite_writer_in_use.writer_service
    service.sqlwriter.hang_copy_task = True


    service.sqlwriter.max_timestamps = 2

    hold_count = 10
    push_trigger = 5
    copy_size = 3
    snap_size = 5
    trigger_offset = hold_count + push_trigger
    async def some_records():
        # Write enough records to make a snapshot
        start_index = await log.get_last_index() + 1
        needed_index = start_index + push_trigger + hold_count
        for i in range(start_index, needed_index+1):
            new_rec = LogRec(index=i, command=f"add {i}", serial=i, term=1)
            rec = await log.insert(new_rec)
            await log.mark_committed(i)
            await log.mark_applied(i)
        # Wait for snapshot processing to complete
        start_time = time.time()
        while time.time() - start_time < 0.5 and await log.lmdb_log.get_snapshot() is None:
            await asyncio.sleep(0.05)

    await some_records()
    snap = await log.lmdb_log.get_snapshot() 
    assert snap is not None, "Snapshot should exist in LMDB"
    assert snap.index == snap_size, f"Snapshot index {snap.index} should be {snap_size}"

    await log.stop()
    start_time = time.time()
    while time.time() - start_time < 0.5 and service.sqlwriter.copy_task_handle:
        await asyncio.sleep(0.05)
    assert not service.sqlwriter.hang_copy_task 
    

async def test_short_stats():

    log = await errors_2_log_setup()
    service = sqlite_writer_in_use.writer_service

    service.sqlwriter.max_timestamps = 4

    hold_count = 10
    push_trigger = 5
    copy_size = 3
    snap_size = 5
    trigger_offset = hold_count + push_trigger
    # Write enough records to overrun timestamps storage, which means a bunch of copy_blocks
    start_index = await log.get_last_index() + 1
    index = start_index
    while len(service.sqlwriter.copy_block_timestamps) < 4:
        new_rec = LogRec(index=index, command=f"add {index}", serial=index, term=1)
        rec = await log.insert(new_rec)
        index += 1
        await asyncio.sleep(0.0001) # time for socket and writer ops
    start_time = time.time()
    while time.time() - start_time < 0.5 and len(service.sqlwriter.copy_block_timestamps) == 4:
        new_rec = LogRec(index=index, command=f"add {index}", serial=index, term=1)
        rec = await log.insert(new_rec)
        index += 1
        await asyncio.sleep(0.0001) # time for socket and writer ops

    assert len(service.sqlwriter.copy_block_timestamps) < 4
    await log.stop()
    start_time = time.time()
    while time.time() - start_time < 0.5 and service.sqlwriter.copy_task_handle:
        await asyncio.sleep(0.05)

async def test_bad_command():
    
    exit_reason = None
    async def cb(reason):
        nonlocal exit_reason
        exit_reason = reason

    logger.info("checking bad command to sqlitewriter")
    
    log = await errors_2_log_setup()
    writer = sqlite_writer_in_use
    service = writer.writer_service
    service.handle_exit_callback = cb
    exit_reason = None
    command = dict(command="explode")
    await log.sw_control.send_command(command)
    
    start_time = time.time()
    while time.time() - start_time < 0.1 and exit_reason is None:
        await asyncio.sleep(0.05)
    assert "unknown" in exit_reason
    assert "explode" in exit_reason
    

async def test_back_channel_errors_1():
    
    exit_reason = None
    async def cb(reason):
        nonlocal exit_reason
        exit_reason = reason

    logger.info("checking unknown response to sqlitecontrol")
    log = await errors_2_log_setup()
    writer = sqlite_writer_in_use
    service = writer.writer_service
    sw_control = log.sw_control
    sw_control.handle_exit_callback = cb
    
    await service.send_message(code="foo", message="")
    start_time = time.time()
    while time.time() - start_time < 0.1 and exit_reason is None:
        await asyncio.sleep(0.05)
    assert "unknown" in str(exit_reason)

    logger.info("checking get_request returns None at sqlitecontrol")
    log = await errors_2_log_setup()
    writer = sqlite_writer_in_use
    service = writer.writer_service
    sw_control = log.sw_control
    sw_control.step_to_break = "get_message"
    sw_control.handle_exit_callback = cb
    exit_reason = None
    
    await service.send_message(code="stats", message="")
    start_time = time.time()
    while time.time() - start_time < 0.1 and exit_reason is None:
        await asyncio.sleep(0.05)
    assert "socket_closed" in exit_reason

    logger.info("checking get_request returns None at sqlitecontrol")
    log = await errors_2_log_setup()
    sw_control = log.sw_control
    sw_control.step_to_break = "get_message"
    sw_control.handle_exit_callback = cb
    exit_reason = None
    
    await service.send_message(code="stats", message="")
    start_time = time.time()
    while time.time() - start_time < 0.1 and exit_reason is None:
        await asyncio.sleep(0.05)
    assert "socket_closed" in exit_reason
        
    for exc in (asyncio.CancelledError('Cancel'), ConnectionResetError('Reset'), Exception('Exc')):
        log = await errors_2_log_setup()
        sw_control = log.sw_control
        sw_control.step_to_break = "get_message"
        sw_control.handle_exit_callback = cb
        sw_control.break_exception = exc
        exit_reason = None
        try:
            await log.get_stats()
        except:
            pass
        start_time = time.time()
        while exit_reason is None and time.time() - start_time < 0.5:
            await asyncio.sleep(0.001)
        if "Exc" == str(exc):
            assert "Exc" in str(exit_reason)
        else:
            assert exit_reason == exc
    
async def test_back_channel_errors_2():
    
    exit_reason = None
    async def cb(reason):
        nonlocal exit_reason
        exit_reason = reason

    # When an exception is raised in get_request, SqliteWriterService.report_fatal_error should
    # be called. It is supposed to send a message on the back channel reporting the error, but
    # that could get an error. Here we simulate that situation and check that the related error handling
    # logic does it's thing
    
    log = await errors_2_log_setup()

    logger.info("checking no length on get_message")
    sw_control = log.sw_control
    sw_control.handle_exit_callback = cb
    wrapper = sw_control.reader
    wrapper.read_no_length = True
    exit_reason = None
    with pytest.raises(asyncio.TimeoutError) as excinfo:
        await log.get_stats()
    assert "socket_closed" in exit_reason

    log = await errors_2_log_setup()

    logger.info("checking no message on get_message")
    sw_control = log.sw_control
    sw_control.handle_exit_callback = cb
    wrapper = sw_control.reader
    wrapper.read_no_message = True
    exit_reason = None
    with pytest.raises(asyncio.TimeoutError) as excinfo:
        await log.get_stats()
    assert "socket_closed" in exit_reason

class BreakingSqliteLog:

    def __init__(self, real_log):
        self.real_log = real_log
        self.fail_stats = False
        
    async def refrest_stats(self):
        if self.fail_stats:
            self.fail_stats = False
            raise Exception("inserted error")
        return await self.real_log.refresh_stats()
    
class SnapBreakHL(HybridLog):
    
    bad_code = False
    error_capture = None
    async def sw_control_callback(self, code, data):
        if self.bad_code:
            code = "foo"
        try:
            res = await super().sw_control_callback(code, data)
        except Exception as e:
            self.error_capture = e
            raise
        return res

async def test_callback_errors(monkeypatch):
        
    path = Path('/tmp', f"test_log_errors")
    if path.exists():
        shutil.rmtree(path)
    path.mkdir()

    hold_count = 10
    push_trigger = 5
    copy_size = 3
    snap_size = 5
    trigger_offset = hold_count + push_trigger
    
    async def setup():
        log = SnapBreakHL(path)
        log.set_hold_count(hold_count)
        log.set_push_trigger(push_trigger)
        await log.set_copy_size(copy_size)
        await log.set_snap_size(snap_size)
        await log.start()

        await log.set_term(1)
        return log

    async def some_records(log):
        # Write enough records to make a snapshot
        start_index = await log.get_last_index() + 1
        needed_index = start_index + push_trigger + hold_count
        for i in range(start_index, needed_index+1):
            new_rec = LogRec(index=i, command=f"add {i}", serial=i, term=1)
            rec = await log.insert(new_rec)
            await log.mark_committed(i)
            await log.mark_applied(i)
        # Wait for snapshot processing to complete
        start_time = time.time()
        while time.time() - start_time < 0.5 and log.error_capture is None:
            await asyncio.sleep(0.05)

    log = await setup()

    # setup to get a bad op code in the snapshot callback
    log.bad_code = True
    await some_records(log)

    assert log.error_capture is not None
    assert "unknown" in str(log.error_capture)

    # setup to get an error processing the snapshot in the snapshot callback
    log = await setup()

    async def mock_refresh_stats(self):
        raise Exception('inserted error')
    
    bound_mock = types.MethodType(mock_refresh_stats, log.sqlite_log)

    monkeypatch.setattr(log.sqlite_log, 'refresh_stats', bound_mock)

    try:
        await some_records(log)
    except Exception as e:
        if not "NoneType" in str(e):
            raise

    
