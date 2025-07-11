from typing import List, Optional, Dict
from datetime import timedelta, date
from decimal import Decimal
from base.datatypes import AccountType, Customer, Account
from base.proxy_api import OpsProxyAPI



class Client:

    def __init__(self, server_proxy: OpsProxyAPI) -> None:
        self.server_proxy = server_proxy
        
    async def create_customer(self, first_name: str, last_name: str, address: str) -> Customer:
        return await self.server_proxy.create_customer(first_name, last_name, address)

    async def create_account(self, customer_id: str, account_type: AccountType) -> Account:
        return await self.server_proxy.create_account(customer_id, account_type)

    async def deposit(self, account_id: int, amount: Decimal) -> Decimal:
        return await self.server_proxy.deposit(account_id, amount)
    
    async def withdraw(self, account_id: int, amount: Decimal) -> Decimal:
        return await self.server_proxy.withdraw(account_id, amount)
    
    async def transfer(self, from_account_id: int, to_account_id: int, amount: Decimal) -> Optional[Dict[str, Decimal]]:
        return await self.server_proxy.transfer(from_account_id, to_account_id, amount)

    async def cash_check(self, account_id: int, amount: Decimal) -> Decimal:
        return await self.server_proxy.cash_check(account_id, amount)
    
    async def list_accounts(self) -> List[Account]:
        return await self.server_proxy.list_accounts()
    
    async def get_accounts(self, customer_id: str) -> List[int]:
        return await self.server_proxy.get_accounts(customer_id)
    
    async def list_statements(self, account_id: int) -> List[date]:
        return await self.server_proxy.list_statements(account_id)
    
    async def advance_time(self, delta_time: timedelta) -> None:
        return await self.server_proxy.advance_time(delta_time)
    
    
