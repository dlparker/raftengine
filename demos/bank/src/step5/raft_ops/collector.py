from typing import List, Optional, Dict, Any
import logging
from datetime import timedelta, date
from decimal import Decimal
from base.datatypes import Customer, Account, AccountType, CommandType
from step5.base_plus.proxy_api import OpsProxyAPI
from base.json_helpers import bank_json_dumps, bank_json_loads

logger = logging.getLogger(__name__)


class Collector(OpsProxyAPI):

    async def create_customer(self, first_name: str, last_name: str, address: str) -> Customer:
        args = locals()
        del args['self']
        return await self.build_command(CommandType.CREATE_CUSTOMER, args)

    async def create_account(self, customer_id: str, account_type: AccountType) -> Account:
        args = locals()
        del args['self']
        return await self.build_command(CommandType.CREATE_ACCOUNT, args)

    async def deposit(self, account_id: int, amount: Decimal) -> Decimal:
        args = locals()
        del args['self']
        return await self.build_command(CommandType.DEPOSIT, args)
    
    async def withdraw(self, account_id: int, amount: Decimal) -> Decimal:
        args = locals()
        del args['self']
        return await self.build_command(CommandType.WITHDRAW, args)
    
    async def transfer(self, from_account_id: int, to_account_id: int, amount: Decimal) -> Optional[Dict[str, Decimal]]:
        args = locals()
        del args['self']
        return await self.build_command(CommandType.TRANSFER, args)

    async def cash_check(self, account_id: int, amount: Decimal) -> Decimal:
        args = locals()
        del args['self']
        return await self.build_command(CommandType.CASH_CHECK, args)
    
    async def list_accounts(self) -> List[Account]:
        args = locals()
        del args['self']
        return await self.build_command(CommandType.LIST_ACCOUNTS, args)
    
    async def get_accounts(self, customer_id: str) -> List[int]:
        args = locals()
        del args['self']
        return await self.build_command(CommandType.GET_ACCOUNTS, args)
    
    async def list_statements(self, account_id: int) -> List[date]:
        args = locals()
        del args['self']
        return await self.build_command(CommandType.LIST_STATEMENTS, args)
    
    async def advance_time(self, delta_time: timedelta) -> None:
        args = locals()
        del args['self']
        return await self.build_command(CommandType.ADVANCE_TIME, args)

    async def raft_message(self, message: str) -> str: # pragma: no cover
        # getting here means we miss wired something
        raise NotImplemented
    
    async def build_command(self, command_name: CommandType, argsdict: Dict[str, Any]) -> Any:
        try:
            # Validate inputs
            if not isinstance(command_name, CommandType):
                raise ValueError(f"command_name must be CommandType, got {type(command_name)}")
            
            logger.debug(f"Building command: {command_name.value} with args: {argsdict}")
            
            # Use .value to get the string representation instead of the enum object
            send_data = dict(command_name=command_name.value, args=argsdict)
            request = bank_json_dumps(send_data)
            
            logger.debug(f"Built command request: {request}")
            return request
            
        except Exception as e:
            logger.error(f"Collector.build_command failed: {e}")
            logger.error(f"command_name: {command_name}, args: {argsdict}")
            raise
        
    
