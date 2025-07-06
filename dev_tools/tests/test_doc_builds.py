#!/usr/bin/env python
import asyncio
import pytest
import logging

# Temp, remove when feature code is done
from dev_tools.build_docs import do_ops
    
async def test_build_docs():
    do_ops(False, False)
