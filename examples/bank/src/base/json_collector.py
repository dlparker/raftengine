"""
This version of the Collector uses the built in python json module and custom actions
to implement the serialization of the TellerProxyAPI. It is a pain, and error prone.
It is provided here for illustration only. All the running code uses the json_pickle
version in collector.py. Each version needs a matching dispatcher.

"""
from typing import List, Optional, Dict, Any
import logging
import json
from datetime import timedelta, date
from decimal import Decimal, ROUND_HALF_UP
from base.datatypes import Customer, Account, AccountType, CommandType
from base.proxy import TellerProxyAPI

logger = logging.getLogger(__name__)

class Collector(TellerProxyAPI):

    def __init__(self, pipe):
        self.pipe = pipe
        
    async def create_customer(self, first_name: str, last_name: str, address: str) -> Customer:
        kwargs = locals()
        del kwargs['self']
        res =  await self.build_command(CommandType.CREATE_CUSTOMER, kwargs)
        return Customer.from_dict(res)

    async def create_account(self, customer_id: str, account_type: AccountType) -> Account:
        kwargs = locals()
        del kwargs['self']
        res = await self.build_command(CommandType.CREATE_ACCOUNT, kwargs)
        return Account.from_dict(res)

    async def deposit(self, account_id: int, amount: Decimal) -> Decimal:
        kwargs = dict(account_id=account_id, amount=float(amount))
        res =  await self.build_command(CommandType.DEPOSIT, kwargs)
        return Decimal(str(res)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    
    async def withdraw(self, account_id: int, amount: Decimal) -> Decimal:
        kwargs = dict(account_id=account_id, amount=float(amount))
        res = await self.build_command(CommandType.WITHDRAW, kwargs)
        return Decimal(str(res)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    
    async def transfer(self, from_account_id: int, to_account_id: int, amount: Decimal) -> Optional[Dict[str, Decimal]]:
        kwargs = dict(from_account_id=from_account_id, to_account_id=to_account_id, amount=float(amount))
        res = await self.build_command(CommandType.TRANSFER, kwargs)
        return res

    async def cash_check(self, account_id: int, amount: Decimal) -> Decimal:
        kwargs = dict(account_id=account_id, amount=float(amount))
        res = await self.build_command(CommandType.CASH_CHECK, kwargs)
        return Decimal(str(res)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    
    async def list_accounts(self) -> List[Account]:
        res = await self.build_command(CommandType.LIST_ACCOUNTS, {})
        result = []
        for item in res:
            result.append(Account.from_dict(item))
        return result
    
    async def get_accounts(self, customer_id: str) -> List[int]:
        return await self.build_command(CommandType.GET_ACCOUNTS, dict(customer_id=customer_id))
    
    async def list_statements(self, account_id: int) -> List[date]:
        kwargs = dict(account_id=account_id)
        res = await self.build_command(CommandType.LIST_STATEMENTS, kwargs)
        result = []
        for x in res:
            result.append(datetime.datetime.fromisoformat(x))
        return result
        
    async def advance_time(self, delta_time: timedelta) -> None:
        args = dict(delta_time=delta_time.total_seconds())
        return await self.build_command(CommandType.ADVANCE_TIME, args)
    
    async def build_command(self, command_name: CommandType, argsdict: Dict[str, Any]) -> Any:
        send_data = dict(command_name=command_name.value, args=argsdict)
        request = json.dumps(send_data)
        res =  await self.pipe.run_command(request)
        res_dict = json.loads(res)
        return res_dict['result']
        
