#!/usr/bin/env python
import logging
from pathlib import Path

import pytest

from raftengine.messages.append_entries import AppendEntriesMessage
from raftengine.api.log_api import LogRec
from dev_tools.memory_log import MemoryLog
from dev_tools.sqlite_log import SqliteLog
from dev_tools.log_control import setup_logging

log_control = setup_logging()
logger = logging.getLogger("test_code")

async def test_log_stuff():
    m_log = MemoryLog()
    m_log.start()

    path = Path('/tmp', "test_log.sqlite")
    if path.exists():
        path.unlink()
    s_log = SqliteLog(path)
    await s_log.start()

    rec1 = LogRec(term=1, command="add 1")
    rec2 = LogRec(term=1, command="add 2")
    msg = AppendEntriesMessage('1', '2', '1', 0, 0, [rec1, rec2], 2)

    #
    
    for log in [m_log, s_log]:

        assert await log.get_last_index() == 0
        assert await log.get_last_term() == 0
        assert await log.get_commit_index() == 0
        assert await log.get_term() == 0
        assert  await log.read() is None

        logger.debug("setting term")
        logger.error("setting term")
        await log.set_term(1)
        rec_1 = await log.append(rec1)
        rec_2 = await log.append(rec2)
        assert await log.get_last_index() == 2
        assert await log.get_last_term() == 1
        assert rec_1.index == 1
        assert rec_1.command == 'add 1'
        assert not rec_1.committed
        assert rec_2.index == 2
        assert rec_2.command == 'add 2'
        
        rec_2b = await log.read(await log.get_last_index())
        assert rec_2b.index == 2
        assert rec_2b.command == 'add 2'
        
        rec_1.committed = True
        await log.replace(rec_1)
        loc_c = await log.get_commit_index()
        assert loc_c == 1
        await log.mark_committed(rec_2)
        loc_c = await log.get_commit_index()
        assert loc_c == 2

        await log.incr_term()
        assert await log.get_term() == 2
        for i in range(3, 20):
            if i == 19:
                await log.set_term(5)
            rec = LogRec(term=await log.get_term(), command=f"add {i}", serial=i)
            rec = await log.append(rec)
            
            if i == 19:
                assert await log.get_last_term() == 5
            else:
                assert await log.get_last_term() == 2
        assert rec.index == 19
        assert await log.get_last_index() == 19
        await log.delete_all_from(4)
        assert await log.read(19) is None
        assert await log.get_last_index() == 3
        assert await log.get_term() == 5
        last_rec = await log.read()
        assert last_rec.index == 3
                                  

        with pytest.raises(Exception):
            await log.read(-3)
        bad_rec = LogRec(index = None, term=await log.get_term(), command=f"add -1", serial=0)
        with pytest.raises(Exception):
            await log.replace(bad_rec)
        bad_rec.index = -1
        with pytest.raises(Exception):
            await log.replace(bad_rec)
        bad_rec.index = 100
        with pytest.raises(Exception):
            await log.replace(bad_rec)

    await m_log.stop()

    
    await s_log.stop()
    new_s_log = SqliteLog(path)
    await new_s_log.start()
    loc_c = await new_s_log.get_commit_index()
    assert loc_c == 2
    rec = await new_s_log.read(2)
    assert rec.index == 2
    assert rec.command == "add 2"

async def test_sqlite_log():

    path = Path('/tmp', "test_log.sqlite")
    if path.exists():
        path.unlink()
    log = SqliteLog(path)
    await log.start()

    assert await log.get_last_index() == 0
    assert await log.get_last_term() == 0
    assert await log.get_commit_index() == 0
    assert await log.get_term() == 0
    assert  await log.read() is None
    await log.set_term(1)
    rec_1 = LogRec(term=1, command="add 1")
    res_rec_1 = await log.append(rec_1)
    rec_2 = LogRec(term=1, command="add 2")
    res_rec_2 = await log.append(rec_2)
    assert await log.get_last_index() == 2
    assert await log.get_last_term() == 1
    assert res_rec_1.index == 1
    assert res_rec_1.command == 'add 1'
    assert not res_rec_1.committed
    assert not res_rec_1.applied
    assert not res_rec_1.committed

    assert res_rec_2.index == 2
    assert res_rec_2.command == 'add 2'
    assert not res_rec_2.committed
    assert not res_rec_2.applied
    
    rec_2b = await log.read(await log.get_last_index())
    for key in res_rec_2.__dict__:
        assert res_rec_2.__dict__[key] == rec_2b.__dict__[key]
    assert rec_2b.index == 2
    assert rec_2b.command == 'add 2'
    
    await log.mark_committed(res_rec_2)
    assert await log.get_commit_index() == 2
    await log.mark_applied(res_rec_1)
    assert await log.get_applied_index() == 1
    
    await log.incr_term()
    assert await log.get_term() == 2
    for i in range(3, 20):
        if i == 19:
            await log.set_term(5)
        rec = LogRec(term=await log.get_term(), command=f"add {i}", serial=i)
        rec = await log.append(rec)

        if i == 19:
            assert await log.get_last_term() == 5
        else:
            assert await log.get_last_term() == 2
    assert rec.index == 19
    assert await log.get_last_index() == 19
    await log.delete_all_from(4)
    assert await log.read(19) is None
    assert await log.get_last_index() == 3
    assert await log.get_term() == 5
    last_rec = await log.read()
    assert last_rec.index == 3


    with pytest.raises(Exception):
        await log.read(-3)
    bad_rec = LogRec(index = None, term=await log.get_term(), command=f"add -1", serial=0)
    with pytest.raises(Exception):
        await log.replace(bad_rec)
    bad_rec.index = -1
    with pytest.raises(Exception):
        await log.replace(bad_rec)
    bad_rec.index = 100
    with pytest.raises(Exception):
        await log.replace(bad_rec)
    await log.stop()
    new_log = SqliteLog(path)
    await new_log.start()
    loc_c = await new_log.get_commit_index()
    assert loc_c == 2
    rec = await new_log.read(2)
    assert rec.index == 2
    assert rec.command == "add 2"
    assert await log.get_last_index() == 3
    assert await log.get_term() == 5
    assert await log.get_applied_index() == 1
    assert await log.get_commit_index() == 2

    import os
    if 'SQLITE_RAFTLOG_PERF_TEST' in os.environ:
        from statistics import mean, stdev
        import time
        log_control.set_default_level('error')
        loop_limit = int(os.environ['SQLITE_RAFTLOG_PERF_TEST'])
        loop_count = 0
        print("\n\n----------------------------\n\n")
        print(f"STARTING PERF TEST {loop_limit} LOOPS")

        times = {
            'loop': [],
            'append': [],
            'read': [],
            'commit': [],
            'apply': [],
            }

        while loop_count < loop_limit:
            # the command cycle is:
            #   1. create log record
            #   2. read it back
            #   3. commit it
            #   4. apply it
            loop_start = time.perf_counter()
            rec = LogRec(term=await log.get_term(), command=f"add {loop_count}", serial=loop_count)
            append_start = time.perf_counter()
            save_rec = await log.append(rec)
            append_end = time.perf_counter()
            read_start = time.perf_counter()
            read_rec = await log.read(save_rec.index)
            read_end = time.perf_counter()
            commit_start = time.perf_counter()
            await log.mark_committed(read_rec)
            commit_end = time.perf_counter()
            apply_start = time.perf_counter()
            await log.mark_applied(read_rec)
            apply_end = time.perf_counter()
            assert await log.get_commit_index() == read_rec.index
            assert await log.get_applied_index() == read_rec.index
            loop_end = time.perf_counter()
            times['loop'].append(loop_end-loop_start)
            times['append'].append(append_end-append_start)
            times['read'].append(read_end-read_start)
            times['commit'].append(commit_end-commit_start)
            times['apply'].append(apply_end-apply_start)
            loop_count += 1

        for key in times:
            k_mean = mean(times[key])
            k_stdev = stdev(times[key])
            total = sum(times[key])
            print(f'{key:10s} total={total:.6f} mean={k_mean:.6f} stdev={k_stdev:.6f}')
        
