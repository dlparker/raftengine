#!/usr/bin/env python
import asyncio
import logging
import pytest
import time
from pathlib import Path
from raftengine.messages.request_vote import RequestVoteMessage,RequestVoteResponseMessage
from raftengine.messages.append_entries import AppendEntriesMessage, AppendResponseMessage
from dev_tools.servers import SNormalElection, SNormalCommand
from dev_tools.servers import setup_logging
from dev_tools.servers import WhenElectionDone
from dev_tools.servers import PausingCluster, cluster_maker

extra_logging = [dict(name=__name__, level="debug"),]
setup_logging(extra_logging)

async def test_log_stuff():
    from raftengine.api.log_api import LogRec,RecordCode, CommandLogRec, ConfigLogRec
    import json
    from raftengine.messages.append_entries import AppendEntriesMessage
    from dev_tools.memory_log import MemoryLog
    from dev_tools.sqlite_log import SqliteLog
    from raftengine.api.log_api import LogRec
    m_log = MemoryLog()
    m_log.start()

    path = Path('/tmp', "test_log.sqlite")
    if path.exists():
        path.unlink()
    s_log = SqliteLog(path)
    s_log.start()

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
        
        await log.set_term(1)
        [rec_1, rec_2] = await log.append_multi([rec1, rec2])
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
        await log.update_and_commit(rec_2)
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

    m_log.close()
    jstring = json.dumps(m_log, default=lambda o:o.__dict__, indent=4)
    jdict = json.loads(jstring)
    new_m_log = MemoryLog.from_json_dict(jdict)
    loc_c = await new_m_log.get_commit_index()
    assert loc_c == 2
    rec = await new_m_log.read(2)
    assert rec.index == 2
    assert rec.command == "add 2"
    
    s_log.close()
    new_s_log = SqliteLog(path)
    new_s_log.start()
    loc_c = await new_s_log.get_commit_index()
    assert loc_c == 2
    rec = await new_s_log.read(2)
    assert rec.index == 2
    assert rec.command == "add 2"
