#!/usr/bin/env python
from pathlib import Path
from base.counters import Counters
from base.validator import Validator
from split_base.collector import Collector
from split_base.dispatcher import Dispatcher
from split_base.pipe import FakeRPCPipe

async def test_counters():
    storage_dir = "/tmp"
    file_path = Path(storage_dir, 'counters.pickle')
    counters = Counters(storage_dir)
    dispatcher = Dispatcher(counters)

    pipe = FakeRPCPipe(dispatcher)
    collector = Collector(pipe)
    
    vt = Validator(collector)


    
