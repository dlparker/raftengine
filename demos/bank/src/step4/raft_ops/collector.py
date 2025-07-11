from typing import List, Optional, Dict, Any
import logging
from datetime import timedelta, date
from decimal import Decimal
from base.datatypes import Customer, Account, AccountType, CommandType
from step4.base_plus.proxy_api import OpsProxyAPI
from base.json_helpers import bank_json_dumps, bank_json_loads

logger = logging.getLogger(__name__)


class Collector(OpsProxyAPI):

    def __init__(self, client):
        self.client = client
        
    async def create_customer(self, first_name: str, last_name: str, address: str) -> Customer:
        args = locals()
        del args['self']
        return await self.do_command(CommandType.CREATE_CUSTOMER, args)

    async def create_account(self, customer_id: str, account_type: AccountType) -> Account:
        args = locals()
        del args['self']
        return await self.do_command(CommandType.CREATE_ACCOUNT, args)

    async def deposit(self, account_id: int, amount: Decimal) -> Decimal:
        args = locals()
        del args['self']
        return await self.do_command(CommandType.DEPOSIT, args)
    
    async def withdraw(self, account_id: int, amount: Decimal) -> Decimal:
        args = locals()
        del args['self']
        return await self.do_command(CommandType.WITHDRAW, args)
    
    async def transfer(self, from_account_id: int, to_account_id: int, amount: Decimal) -> Optional[Dict[str, Decimal]]:
        args = locals()
        del args['self']
        return await self.do_command(CommandType.TRANSFER, args)

    async def cash_check(self, account_id: int, amount: Decimal) -> Decimal:
        args = locals()
        del args['self']
        return await self.do_command(CommandType.CASH_CHECK, args)
    
    async def list_accounts(self) -> List[Account]:
        args = locals()
        del args['self']
        return await self.do_command(CommandType.LIST_ACCOUNTS, args)
    
    async def get_accounts(self, customer_id: str) -> List[int]:
        args = locals()
        del args['self']
        return await self.do_command(CommandType.GET_ACCOUNTS, args)
    
    async def list_statements(self, account_id: int) -> List[date]:
        args = locals()
        del args['self']
        return await self.do_command(CommandType.LIST_STATEMENTS, args)
    
    async def advance_time(self, delta_time: timedelta) -> None:
        args = locals()
        del args['self']
        return await self.do_command(CommandType.ADVANCE_TIME, args)

    async def raft_message(self, message: str) -> str: # pragma: no cover
        # getting here means we miss wired something
        raise NotImplemented
    
    async def do_command(self, command_name: CommandType, argsdict: Dict[str, Any]) -> Any:
        send_data = dict(command_name=command_name, args=argsdict)
        request = bank_json_dumps(send_data)
        logger.debug("Calling client raft_message")
        result = await self.client.raft_message(request)
        return bank_json_loads(result)
        
    
