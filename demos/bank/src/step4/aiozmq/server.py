import argparse
import asyncio
from pathlib  import Path
from typing import List, Optional, Dict
from datetime import timedelta, date
from decimal import Decimal
import aiozmq.rpc

from base.datatypes import Customer, Account, AccountType
from base.proxy_api import OpsProxyAPI
from base.operations import Ops
from base.msgpack_helpers import BankPacker, get_bank_translation_table


class Server(aiozmq.rpc.AttrHandler):
    """
    """

    def __init__(self, server):
        self.server = server
        
    @aiozmq.rpc.method
    async def create_customer(self, first_name: str, last_name: str, address: str) -> Customer:
        return await self.server.create_customer(first_name, last_name, address)

    @aiozmq.rpc.method
    async def create_account(self, customer_id: str, account_type: AccountType) -> Account:
        return await self.server.create_account(customer_id, account_type)

    @aiozmq.rpc.method
    async def deposit(self, account_id: int, amount: Decimal) -> Decimal:
        return await self.server.deposit(account_id, amount)
    
    @aiozmq.rpc.method
    async def withdraw(self, account_id: int, amount: Decimal) -> Decimal:
        return await self.server.withdraw(account_id, amount)
    
    @aiozmq.rpc.method
    async def transfer(self, from_account_id: int, to_account_id: int, amount: Decimal) -> Optional[Dict[str, Decimal]]:
        return await self.server.transfer(from_account_id, to_account_id, amount)

    @aiozmq.rpc.method
    async def cash_check(self, account_id: int, amount: Decimal) -> Decimal:
        return await self.server.cash_check(account_id, amount)
    
    @aiozmq.rpc.method
    async def list_accounts(self) -> List[Account]:
        return await self.server.list_accounts()
    
    @aiozmq.rpc.method
    async def get_accounts(self, customer_id: str) -> List[int]:
        return await self.server.get_accounts(customer_id)
    
    @aiozmq.rpc.method
    async def list_statements(self, account_id: int) -> List[date]:
        return await self.server.list_statements(account_id)
    
    @aiozmq.rpc.method
    async def advance_time(self, delta_time: timedelta) -> None:
        return await self.server.advance_time(delta_time)


async def create_server(host: str, port: int, handler):
    """Create an aiozmq RPC server with custom msgpack serialization"""
    translation_table = get_bank_translation_table()
    server = await aiozmq.rpc.serve_rpc(
        handler,
        bind=f'tcp://{host}:{port}',
        translation_table=translation_table
    )
    return server
