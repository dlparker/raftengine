import asyncio
import time
import sys
import json
from random import randint
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

logger = logging.getLogger('HybridLog.sqlite_writer')


class SqliteWriterControl:

    def __init__(self, sqlite_db_path, lmdb_db_path, snap_size, copy_block_size):
        self.sqlite_db_path = sqlite_db_path
        self.lmdb_db_path = lmdb_db_path
        self.snap_size = snap_size
        self.copy_block_size = copy_block_size
        self.record_list = None
        self.port = None
        self.writer_proc = None
        self.reader = None
        self.writer = None
        self.running = False
        self.callback = None
        self.error_callback = None
        self.writer_task = None

    async def start(self, callback, error_callback, port=None, inprocess=False):
        self.callback = callback
        self.error_callback = error_callback
        if port is None:
            port = randint(8000, 65000)
        self.port = port
        if inprocess:
            # This is just for testing support, having it run
            # in process helps with debugging and coverage.
            # It is not appropriate for actual use as you'll
            # lose all the benifit of the hybrid approach
            self.writer_task = asyncio.create_task(
                writer_task(self.sqlite_db_path, self.lmdb_db_path, self.port, self.snap_size, self.copy_block_size))
            await asyncio.sleep(0.01)
            logger.warning("sqlwriter Task started, test and debug only!!!")
        else:
            args = [self.sqlite_db_path, self.lmdb_db_path, self.port, self.snap_size, self.copy_block_size]
            self.writer_proc = Process(target=writer_process, args=args)
            self.writer_proc.start()
            await asyncio.sleep(0.01)
            logger.debug("sqlwriter process started")
        self.running = True
        self.reader, self.writer = await asyncio.open_connection('localhost', self.port)
        asyncio.create_task(self.read_backchannel())

    async def stop(self):
        self.running = False
        if self.writer:
            await self.send_quit()
            await asyncio.sleep(0.001)
        if self.writer_proc:
            self.writer_proc.join()
            self.writer_proc = None
        if self.writer_task: # pragma: no cover   this is test only code, production uses proc
            try:
                self.writer_task.cancel()
            except asyncio.CancelledError:
                pass
            except ConnectionResetError:
                pass

    async def send_command(self, command):
        msg_str = json.dumps(command)
        msg_bytes = msg_str.encode()
        count = str(len(msg_bytes))
        self.writer.write(f"{count:20s}".encode())
        self.writer.write(msg_bytes)
        await self.writer.drain()
        
    async def send_limit(self, limit, commit_index, apply_index):  
        command = dict(command='copy_limit', limit=limit, commit_index=commit_index, apply_index=apply_index)
        await self.send_command(command)
        
    async def send_hard_push(self, last_index, commit_index, apply_index):  
        command = dict(command='hard_push', last_index=last_index, commit_index=commit_index, apply_index=apply_index)
        await self.send_command(command)
        
    async def set_snap_size(self, size):
        self.snap_size = size
        if self.writer:
            command = dict(command='snap_size', size=size)
            await self.send_command(command)
        
    async def set_copy_block_size(self, size):
        self.copy_block_size = size
        if self.writer:
            command = dict(command='copy_block_size', size=size)
            await self.send_command(command)
        
    async def send_note_delete(self, new_last):
        command = dict(command='note_delete', new_last=new_last)
        await self.send_command(command)
        
    async def send_quit(self):
        command = dict(command='quit')
        await self.send_command(command)

    async def get_message(self):
        len_data = await self.reader.read(20)
        if not len_data:
            logger.warning("Connection closed by sqlwriter while reading length")
            return None
        msg_len = int(len_data.decode().strip())
        data = await self.reader.read(msg_len)
        if not data:
            logger.warning("No data received, sqlwriter connection closed while reading message")
            return None
        msg_wrapper = json.loads(data.decode())
        logger.debug("read_backchannel message %s", msg_wrapper)
        return msg_wrapper
                    
    async def read_backchannel(self):
        logger.debug('read_backchannel started')
        exit_reason = None
        try:
            while self.running:
                msg_wrapper = await self.get_message()
                if msg_wrapper is None:
                    exit_reason = "socket_closed"
                    break
                if msg_wrapper['code'] == "quitting":
                    logger.warning(f'writer process sent quitting signal, shutting down')
                    exit_reason = "quitting"
                    break
                elif msg_wrapper['code'] == "snapshot":
                    snap = msg_wrapper['message']
                    snapshot = SnapShot(snap['index'], snap['term'])
                    logger.debug('\n--------------------\nhandling reply snapshot %s\n----------------------\b', str(snapshot))
                    await self.callback("snapshot", snapshot)
                elif msg_wrapper['code'] == "stats":
                    stats = msg_wrapper['message']
                    logger.debug('handling reply stats %s', stats)
                    asyncio.create_task(self.callback("stats", stats))
                elif msg_wrapper['code'] == "fatal_error":
                    logger.debug("Got error in backchannel \n%s", msg_wrapper['message'])
                    raise Exception(f"Error from sqlwriter \n {msg_wrapper['message']}")
                else:
                    logger.error('\n--------------------\nhandling reply message code unknown %s\n----------------------\b',
                                 msg_wrapper['code'])
                    raise Exception(f"Error from sqlwriter, unknown message code {msg_wrapper['code']}")
        except asyncio.CancelledError as e:
            logger.warning('read_backchannel got cancelled')
            exit_reason = e
        except ConnectionResetError as e:
            logger.warning('read_backchannel got dropped socket')
            exit_reason = e
        except Exception as e:
            logger.error('read_backchannel got error \n%s', traceback.format_exc())
            exit_reason = e
            asyncio.create_task(self.error_callback(traceback.format_exc()))
        await self.stop()
        return exit_reason


class SqliteWriter:

    def __init__(self, sqlite_db_path, lmdb_db_path, port, snap_size, copy_block_size):
        self.sqlite_db_path = sqlite_db_path
        self.lmdb_db_path = lmdb_db_path        
        self.port = port
        self.snap_size = snap_size
        self.copy_block_size = copy_block_size
        self.writer_service = SqliteWriterService(self, port=self.port)
        from .hybrid_log import LMDB_MAP_SIZE
        self.sqlite = SqliteLog(self.sqlite_db_path, enable_wal=True)
        self.lmdb = LmdbLog(self.lmdb_db_path, map_size=LMDB_MAP_SIZE)
        self.started = False
        self.stopped = False
        self.copy_limit = 0
        self.last_snap_index = 0
        self.copy_task_handle = None
        self.upstream_commit_index = 0
        self.upstream_apply_index = 0
        # Rate tracking fields for statistics
        self.copy_block_timestamps = []  # For blocks_per_minute calculation
        self.max_timestamps = 1000
        self.copy_blocks_count = 0

    async def start(self):
        if not self.started:
            await self.sqlite.start()
            await self.lmdb.start()
            await self.writer_service.start()
            self.started = True

    async def serve(self):
        await self.writer_service.serve()
        logger.debug("Sqlwriter.serve() exited")
        await self.stop()

    async def stop(self):
        if not self.stopped:
            if self.copy_task_handle:
                self.copy_task_handle.cancel()
                try:
                    await self.copy_task_handle
                except asyncio.CancelledError:
                    pass
                self.copy_task_handle = None
            await self.sqlite.stop()
            await self.lmdb.stop()
            self.sqlite = None
            self.lmdb = None
            self.stopped = True
        
    async def set_snap_size(self, size):
        self.snap_size = size
        
    async def handle_deletes(self, new_last):
        if self.lmdb.records is not None: 
            await self.lmdb.stop()
        await self.lmdb.start()
        self.upstream_commit_index = min(new_last, self.upstream_commit_index)
        self.upstream_apply_index = min(new_last, self.upstream_apply_index)
        logger.debug("after note delete last_commit = %d, last_apply = %d",
                     self.upstream_commit_index, self.upstream_apply_index)
        
    async def set_copy_limit(self, props):
        limit = props['limit']
        self.upstream_commit_index = props['commit_index']
        self.upstream_apply_index = props['apply_index']
        self.copy_limit = limit
        if not self.copy_task_handle:
            self.copy_task_handle = asyncio.create_task(self.copy_task())
            logger.debug("Started copy task with limit %d", limit)
        return None
    
    async def hard_push(self, props):
        return await self.hard_push_task()
    
    async def get_stats(self) -> dict:
        """Get writer-side statistics"""
        import time
        current_time = time.time()
        five_minutes_ago = current_time - 300
        
        # Clean old timestamps and calculate rate
        self.copy_block_timestamps = [ts for ts in self.copy_block_timestamps if ts >= five_minutes_ago]
        copy_blocks_per_minute = len(self.copy_block_timestamps) * 12  # Convert to per-minute
        
        sqlite_commit = await self.sqlite.get_commit_index()
        sqlite_apply = await self.sqlite.get_applied_index()
        
        return {
            'current_copy_limit': self.copy_limit,
            'upstream_commit_lag': self.upstream_commit_index - sqlite_commit,
            'upstream_apply_lag': self.upstream_apply_index - sqlite_apply,
            'copy_blocks_per_minute': copy_blocks_per_minute
        }
    
    async def copy_block(self, first_index, last_index):
        logger.debug("SqliteWriterService copy task copying from %d to %d", first_index, last_index)
        recs = []
        for index in range(first_index, last_index+1):
            rec = await self.lmdb.read(index)
            if rec:
                recs.append(rec)
        local_term = await self.sqlite.get_term()
        for rec in recs:
            await self.sqlite.insert(rec)
        # update local stats from new record efects
        logger.debug("SqliteWriterService copy block finished copying from %d to %d",
                     first_index, last_index)
        return 
        
    async def copy_task(self):
        try:
            if self.lmdb.records is not None: 
                await self.lmdb.stop()
            await self.lmdb.start()
            await self.sqlite.refresh_stats()
            my_last = await self.sqlite.get_last_index()
            if my_last == 0:
                my_last = 1
            logger.debug("SqliteWriterService copy task starting with last index %d, limit = %d copy_block_size %d",
                         my_last, self.copy_limit, self.copy_block_size)
            start_index = my_last
            while my_last < self.copy_limit:
                if self.copy_limit - my_last > self.copy_block_size:
                    await self.copy_block(my_last, my_last + self.copy_block_size)
                else:
                    await self.copy_block(my_last, self.copy_limit)
                max_index = await self.sqlite.get_last_index()
                max_term = await self.sqlite.get_last_term()
                await self.sqlite.set_term(max_term)
                local_commit = await self.sqlite.get_commit_index()
                local_apply = await self.sqlite.get_applied_index()
                if self.upstream_commit_index > local_commit:
                    max_commit = min(self.upstream_commit_index, max_index)
                    await self.sqlite.mark_committed(max_commit)
                    logger.debug("updated sqlite commit to %d", max_commit)
                if self.upstream_apply_index > local_apply:
                    max_apply = min(self.upstream_apply_index, max_index)
                    await self.sqlite.mark_applied(max_apply)
                    logger.debug("updated sqlite applied to %d", max_apply)
                # Track copy block rate for statistics
                self.copy_blocks_count += 1
                self.copy_block_timestamps.append(time.time())
                # Limit list size for memory efficiency
                if len(self.copy_block_timestamps) > self.max_timestamps:
                    self.copy_block_timestamps = self.copy_block_timestamps[self.max_timestamps//2:]
                
                my_last = await self.sqlite.get_last_index()

            # Figure out how much to snapshot. Relevant points:
            # The last snapshot in lmdb, if any, tells us the low
            # water mark. If none, then low water is 1. The
            # Sqlite max index is high water mark. The limit
            # for snapshot size is defined. So, if high water
            # minus low water is greater than or equal to snap_size,
            # we snap up to snap_size. We keep doing that if necessary
            # until we catch up with copy_limit. Copy limit is
            # determined by the HybridLog main class based on
            # current record count and the hold_count configuration
            lmdb_snap = await self.lmdb.get_snapshot()
            low_water = 1 if lmdb_snap is None else lmdb_snap.index + 1
            high_water = my_last
            logger.debug("Snapshot check low_water = %d, high_water = %d, snap_size = %d",
                         low_water, high_water, self.snap_size)
            while high_water - low_water >= self.snap_size:
                to_send = min(high_water-low_water, self.snap_size)
                logger.debug("Doing snapshot for low_water = %d, high_water = %d, snap_size = %d, to_send = %d",
                             low_water, high_water, self.snap_size, to_send)
                snap_index = low_water - 1 + to_send # we are snapping from low_water inclusive
                snap_rec = await self.sqlite.read(snap_index)
                snapshot = SnapShot(snap_rec.index, snap_rec.term)
                logger.debug('sending %s', str(snapshot))
                await self.writer_service.send_message(code="snapshot", message=snapshot)
                low_water = snap_index + 1
        except Exception as e:
            await self.writer_service.report_fatal_error(traceback.format_exc())
            self.copy_task_handle = None
            await self.stop()
            
        self.copy_task_handle = None
                    
    async def hard_push_task(self):
        try:
            if self.lmdb.records is not None: 
                await self.lmdb.stop()
            await self.lmdb.start()
            await self.sqlite.refresh_stats()
            sqlite_last = await self.sqlite.get_last_index()
            lmdb_last = await self.lmdb.get_last_index()
            if sqlite_last == lmdb_last:
                return
            copied = 0
            start_index = sqlite_last + 1
            end_index = lmdb_last
            logger.debug("Starting hard push loop for index %d to %d", start_index, end_index)
            copied = 0
            while start_index < end_index:
                to_copy = end_index - start_index 
                if to_copy > self.copy_limit:
                    to_copy = self.copy_limit
                await self.copy_block(start_index, start_index + to_copy)
                copied += to_copy
                # We have to restart lmdb because there is some issue
                # with multiprocess access, our copy gets stale
                await self.lmdb.stop() 
                await self.lmdb.start()
                end_index = await self.lmdb.get_last_index()
                start_index = await self.sqlite.get_last_index() + 1
            if copied > 0:
                snap_index = end_index
                snap_rec = await self.sqlite.read(snap_index)
                snapshot = SnapShot(snap_rec.index, snap_rec.term)
                logger.debug('sending %s', str(snapshot))
                await self.writer_service.send_message(code="snapshot", message=snapshot)
            return 
        except:
            logger.error("Hard push task got error\n%s", traceback.format_exc())
            

def writer_process(sqlite_file_path, lmdb_db_path, port, snap_size, copy_block_size): # pragma: no cover can't get coverage on mp
    # this is the main function of the writer process
    async def run():
        writer = SqliteWriter(sqlite_file_path, lmdb_db_path, port, snap_size, copy_block_size)
        await writer.start()
        await writer.serve()
    asyncio.run(run())
    logger.debug("writer process exiting")

async def writer_task(sqlite_file_path, lmdb_db_path, port, snap_size, copy_block_size):
    # This is just for testing support, having it run
    # in process helps with debugging and coverage.
    # It is not appropriate for actual use as you'll
    # lose all the benifit of the hybrid approach
    writer = SqliteWriter(sqlite_file_path, lmdb_db_path, port, snap_size, copy_block_size)
    await writer.start()
    await writer.serve()

class SqliteWriterService:

    def __init__(self, sqlwriter, port):
        self.sqlwriter = sqlwriter
        self.port = port
        self.sock_server = None
        self.server_task = None
        self.shutdown_event = asyncio.Event()
        self.running = False
        self.writer = None
        self.reader = None
        self.fatal_error = None # tracking what happens for test support only

    async def start(self):
        self.running = True
        logger.info("starting server on port %d", self.port)
        self.sock_server = await asyncio.start_server(
            self.handle_client, '127.0.0.1', self.port
        )
        
    async def serve(self):
        logger.info("SqliteWriterService listening on %d", self.port)
        try:
            # Keep the server running
            await self.shutdown_event.wait()
            logger.debug("serve got shutdown")
        except asyncio.CancelledError:
            # Server is being shut down
            pass
        finally:
            if self.sock_server:
                self.sock_server.close()
                self.sock_server = None
        logger.info("SqliteWriterService exiting")
        self.server_task = None
        self.running = False
        
    async def stop(self):
        self.shutdown_event.set()

    async def report_fatal_error(self, error):
        try:
            self.fatal_error = f"{error}"
            await self.send_message('fatal_error', error)
            logger.error('Reporting fatal error \n%s', error)
        except:
            logger.error('Trying to report fatal error got %s', traceback.format_exc())
            self.fatal_error += f" {traceback.format_exc()}"
        try:
            await self.stop()
        except:
            self.fatal_error += f" {traceback.format_exc()}"
            if self.sock_server:
                try:
                    self.sock_server.close()
                except:
                    self.fatal_error += f" {traceback.format_exc()}"
                    pass
                
    async def send_message(self, code, message):
        wrapper = dict(code=code, message=message)
        msg = json.dumps(wrapper, default=lambda o: o.__dict__)
        msg = msg.encode()
        count = str(len(msg))
        self.writer.write(f"{count:20s}".encode())
        self.writer.write(msg)
        await self.writer.drain()
        
    async def get_request(self):
        len_data = await self.reader.read(20)
        if not len_data:
            logger.debug("SqliteWriterService got None on initial read")
            return None
        msg_len = int(len_data.decode().strip())
        # Read message data
        data = await self.reader.read(msg_len)
        if not data:
            logger.debug("SqliteWriterService got None on length read")
            return None
        request = json.loads(data.decode())
        return request

    async def handle_request(self, request):
        if request['command'] == 'quit':
            logger.info("quitting on command")
            await self.send_message(code="quitting", message="")
            await asyncio.sleep(0.001)
            return False
        elif request['command'] == 'snap_size':
            new_size = int(request['size'])
            logger.debug("SqliteWriterService got new snap_size %d", new_size)
            await self.sqlwriter.set_snap_size(new_size)
            return True
        elif request['command'] == 'copy_block_size':
            new_size = int(request['size'])
            logger.debug("SqliteWriterService got new copy_block_size %d", new_size)
            self.sqlwriter.copy_block_size = int(new_size)
            return True
        elif request['command'] == 'note_delete':
            new_last = int(request['new_last'])
            logger.debug("SqliteWriterService got new last index %d after delete", new_last)
            await self.sqlwriter.handle_deletes(new_last)
            return True
        elif request['command'] == 'copy_limit':
            await self.sqlwriter.set_copy_limit(request)
            logger.debug("SqliteWriterService got copy limit")
            return True
        elif request['command'] == 'hard_push':
            logger.debug("SqliteWriterService got hard push")
            await self.sqlwriter.hard_push(request)
            return True
        elif request['command'] == 'get_stats':
            logger.debug("SqliteWriterService got get stats")
            stats = await self.sqlwriter.get_stats()
            await self.send_message(code="stats", message=stats)
            return True
        raise Exception(f'Got request of unknown type {request}')
        
    async def handle_client(self, reader, writer):
        # intended to handle exactly one connection, more is improper usage
        logger.debug("SqliteWriterService connection from %s", writer.get_extra_info("peername"))
        self.writer = writer
        self.reader = reader
        exit_reason = None
        while self.running:
            try:
                # Doing the work via these methods makes it much
                # easier to write tests for the code in them..
                request = await self.get_request()
                if request is None:
                    exit_reason = "socket_closed"
                    break
                # there is some logic that implicitly expexts
                # requests to be handled sequentially (such
                # as deleting records expecting copy to be done first)
                # so don't do anything to allow that to change
                go_flag = await self.handle_request(request)
                if not go_flag:
                    exit_reason = "on_request"
                    break
                #logger.debug("SqliteWriterService got request %s", request)
            except asyncio.CancelledError as e:
                logger.warning("SqliteWriterService handler canceled")
                exit_reason = e
                break
            except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError) as e:
                logger.error("SqliteWriterService handler error \n%s", traceback.format_exc())
                exit_reason = e
                break
            except Exception as e:
                msg = f"SqliteWriterService handler error\n{traceback.format_exc()}"
                exit_reason = e
                return await self.report_fatal_error(msg)
        await self.stop()
        logger.warning("SqliteWriterService handler exiting")
        return exit_reason
    
    
