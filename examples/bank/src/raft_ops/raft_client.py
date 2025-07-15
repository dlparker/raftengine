import argparse
import asyncio
from pathlib  import Path
from typing import List, Optional, Dict, Callable, Any
from datetime import timedelta, date
from decimal import Decimal
from functools import wraps
from base.datatypes import Customer, Account, AccountType
from base.rpc_api import RPCAPI
from raftengine.api.deck_api import CommandResult


class RaftClient(RPCAPI):
    """
    """

    def __init__(self, rpc_client, client_maker):
        uri = rpc_client.get_uri()
        self.current_leader = uri
        self.rpc_clients = dict(uri=rpc_client)
        self.rpc_client = rpc_client
        
    async def get_uri(self):
        return self.current_leader

    async def get_rpc_client(self):
        return self.rpc_client
    
    async def set_new_leader(self, uri):
        if uri not in self.rpc_clients:
            self.rpc_clients[uri] = client_maker(uri)
            self.current_leader = uri
            self.rpc_client = self.rpc_clients[uri]
        return self.rpc_clients[uri]

    async def raft_message(self, message:str) -> None:
        return await self.rpc_client.raft_message(message)
        
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
