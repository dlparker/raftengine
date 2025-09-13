#!/usr/bin/env python
from pathlib import Path
from base.counters import Counters
from base.validator import Validator

async def test_counters():
    storage_dir = "/tmp"
    file_path = Path(storage_dir, 'counters.pickle')
    counters = Counters(storage_dir)
    vt = Validator(counters)


    
