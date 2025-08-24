#!/usr/bin/env python
import asyncio
import pytest
import logging
from typing import Any
from log_control import setup_logging

controller = setup_logging()
logger = controller.add_logger("test_code")

import ops
from ops.cluster_cmd import ClusterCLI

async def test_setup():
    logger.debug("debug logging")
    ccli = ClusterCLI()
    result = await ccli._logic_find_clusters(search_dir="/tmp", return_json=True)

