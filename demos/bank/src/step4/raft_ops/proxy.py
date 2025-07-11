import argparse
import asyncio
from pathlib  import Path
from typing import List, Optional, Dict
from datetime import timedelta, date
from decimal import Decimal
from base.datatypes import Customer, Account, AccountType
from step4.base_plus.proxy_api import OpsProxyAPI
from step4.raft_ops.collector import Collector


class ServerProxy(OpsProxyAPI):
    """
    """

    def __init__(self, collector:Collector):
        self.collector = collector
        
    async def create_customer(self, first_name: str, last_name: str, address: str) -> Customer:
        return await self.collector.create_customer(first_name, last_name, address)

    async def create_account(self, customer_id: str, account_type: AccountType) -> Account:
        return await self.collector.create_account(customer_id, account_type)

    async def deposit(self, account_id: int, amount: Decimal) -> Decimal:
        return await self.collector.deposit(account_id, amount)
    
    async def withdraw(self, account_id: int, amount: Decimal) -> Decimal:
        return await self.collector.withdraw(account_id, amount)
    
    async def transfer(self, from_account_id: int, to_account_id: int, amount: Decimal) -> Optional[Dict[str, Decimal]]:
        return await self.collector.transfer(from_account_id, to_account_id, amount)

    async def cash_check(self, account_id: int, amount: Decimal) -> Decimal:
        return await self.collector.cash_check(account_id, amount)
    
    async def list_accounts(self) -> List[Account]:
        return await self.collector.list_accounts()
    
    async def get_accounts(self, customer_id: str) -> List[int]:
        return await self.collector.get_accounts(customer_id)
    
    async def list_statements(self, account_id: int) -> List[date]:
        return await self.collector.list_statements(account_id)
    
    async def advance_time(self, delta_time: timedelta) -> None:
        return await self.collector.advance_time(delta_time)

    async def raft_message(self, message: str) -> str: # pragma: no cover
        return await self.collector.raft_message(message)
        
