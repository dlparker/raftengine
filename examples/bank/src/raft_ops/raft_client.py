import argparse
import asyncio
from pathlib  import Path
from typing import List, Optional, Dict, Callable, Any
import time
from datetime import timedelta, date
from decimal import Decimal
from functools import wraps
from raftengine.api.types import CommandResult
from raftengine.deck.log_control import LogController
from base.datatypes import Customer, Account, AccountType
from base.rpc_api import RPCAPI

log_controller = LogController.get_controller()
logger = log_controller.add_logger("raft_ops.RaftClient",
                                   "Client layer that adds redirect and retry logic to RPC client")

class RaftClient(RPCAPI):
    """
    """

    def __init__(self, rpc_client, rpc_helper):
        uri = rpc_client.get_uri()
        self.current_leader = uri
        self.rpc_clients = dict(uri=rpc_client)
        self.rpc_client = rpc_client
        self.rpc_helper = rpc_helper()
        self.client_maker = self.rpc_helper.rpc_client_maker
        
    async def get_uri(self):
        return self.current_leader

    async def get_rpc_client(self):
        return self.rpc_client
    
    async def set_new_leader(self, uri):
        if uri not in self.rpc_clients:
            self.rpc_clients[uri] = await self.client_maker(uri)
            self.current_leader = uri
            self.rpc_client = self.rpc_clients[uri]
            logger.info("setting new leader %s", uri)
            print("")
        return self.rpc_clients[uri]

    # called by Collector
    async def raft_message(self, message:str) -> None:
        return await self.rpc_client.raft_message(message)
        
    # called by Collector
    async def run_command(self, command:str) -> CommandResult:
        result = await self.rpc_client.run_command(command)
        if result.result:
            return result.result
        if result.error:
            raise Exception(f'got error from server {result.error}')
        if result.timeout_expired:
            raise Exception(f'got timeout at server, cluster not available')
        if result.redirect:
            await self.set_new_leader(result.redirect)
            return await self.run_command(command)
        if not result.retry:
            raise Exception(f"Command result does not make sense {result.__dict__}")
        start_time = time.time()
        while result.retry and time.time() - start_time < 1.0:
            await asyncio.sleep(0.0001)
            result = await self.rpc_client.run_command(command)
        if result.retry:
            raise Exception('could not process message at server, cluster not available')

    # called by LocalCollector
    async def local_command(self, command:str) -> str:
        return await self.rpc_client.local_command(command)
    
