import argparse
import asyncio
from pathlib  import Path
from typing import List, Optional, Dict
from datetime import timedelta, date
from decimal import Decimal
from base.datatypes import Customer, Account, AccountType
from base.proxy_api import ProxyAPI
from base.operations import Ops

class ServerProxy(ProxyAPI):
    """
    Implementation of base.proxy.ProxyAPI that has a base.operations.Ops instance
    and makes direct calls to it. This is of no practical value in a finished
    application, it is used in this demo just to show an initial step that
    ensures that your client code can use the services that your sevice code
    provides by proxy.
    """

    def __init__(self, server:Ops):
        self.server = server
        
    async def create_customer(self, first_name: str, last_name: str, address: str) -> Customer:
        return await self.server.create_customer(first_name, last_name, address)

    async def create_account(self, customer_id: str, account_type: AccountType) -> Account:
        return await self.server.create_account(customer_id, account_type)

    async def deposit(self, account_id: int, amount: Decimal) -> Decimal:
        return await self.server.deposit(account_id, amount)
    
    async def withdraw(self, account_id: int, amount: Decimal) -> Decimal:
        return await self.server.withdraw(account_id, amount)
    
    async def transfer(self, from_account_id: int, to_account_id: int, amount: Decimal) -> Optional[Dict[str, Decimal]]:
        return await self.server.transfer(from_account_id, to_account_id, amount)

    async def cash_check(self, account_id: int, amount: Decimal) -> Decimal:
        return await self.server.cash_check(account_id, amount)
    
    async def list_accounts(self) -> List[Account]:
        return await self.server.list_accounts()
    
    async def get_accounts(self, customer_id: str) -> List[int]:
        return await self.server.get_accounts(customer_id)
    
    async def list_statements(self, account_id: int) -> List[date]:
        return await self.server.list_statements(account_id)
    
    async def advance_time(self, delta_time: timedelta) -> None:
        return await self.server.advance_time(delta_time)
