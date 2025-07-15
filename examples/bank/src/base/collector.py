from typing import List, Optional, Dict, Any
import logging
from datetime import timedelta, date
from decimal import Decimal
from base.datatypes import Customer, Account, AccountType, CommandType
from base.proxy import TellerProxyAPI
import jsonpickle

logger = logging.getLogger(__name__)

class Collector(TellerProxyAPI):
    def __init__(self, pipe):
        self.pipe = pipe
        # Configure jsonpickle for clean output
        jsonpickle.set_encoder_options('json', indent=2, sort_keys=True)

    async def create_customer(self, first_name: str, last_name: str, address: str) -> Customer:
        command = Command(command_name=CommandType.CREATE_CUSTOMER, args=CustomerArgs(first_name=first_name, last_name=last_name, address=address))
        return await self.build_command(command, Customer)

    async def create_account(self, customer_id: str, account_type: AccountType) -> Account:
        command = Command(command_name=CommandType.CREATE_ACCOUNT, args=AccountArgs(customer_id=customer_id, account_type=account_type))
        return await self.build_command(command, Account)

    async def deposit(self, account_id: int, amount: Decimal) -> Decimal:
        command = Command(command_name=CommandType.DEPOSIT, args=DepositArgs(account_id=account_id, amount=amount))
        return await self.build_command(command, Decimal)

    async def withdraw(self, account_id: int, amount: Decimal) -> Decimal:
        command = Command(command_name=CommandType.WITHDRAW, args=WithdrawArgs(account_id=account_id, amount=amount))
        return await self.build_command(command, Decimal)

    async def transfer(self, from_account_id: int, to_account_id: int, amount: Decimal) -> Optional[Dict[str, Decimal]]:
        command = Command(command_name=CommandType.TRANSFER, args=TransferArgs(from_account_id=from_account_id, to_account_id=to_account_id, amount=amount))
        return await self.build_command(command, Optional[Dict[str, Decimal]])

    async def cash_check(self, account_id: int, amount: Decimal) -> Decimal:
        command = Command(command_name=CommandType.CASH_CHECK, args=CashCheckArgs(account_id=account_id, amount=amount))
        return await self.build_command(command, Decimal)

    async def list_accounts(self) -> List[Account]:
        command = Command(command_name=CommandType.LIST_ACCOUNTS, args={})
        return await self.build_command(command, List[Account])

    async def get_accounts(self, customer_id: str) -> List[int]:
        command = Command(command_name=CommandType.GET_ACCOUNTS, args=GetAccountsArgs(customer_id=customer_id))
        return await self.build_command(command, List[int])

    async def list_statements(self, account_id: int) -> List[date]:
        command = Command(command_name=CommandType.LIST_STATEMENTS, args=ListStatementsArgs(account_id=account_id))
        return await self.build_command(command, List[date])

    async def advance_time(self, delta_time: timedelta) -> None:
        command = Command(command_name=CommandType.ADVANCE_TIME, args=AdvanceTimeArgs(delta_time=delta_time))
        await self.build_command(command, None)

    async def build_command(self, command: 'Command', return_type: Any) -> Any:
        # Serialize command object to JSON
        request = jsonpickle.encode(command)
        response = await self.pipe.run_command(request)
        unpacked = jsonpickle.decode(response)
        return unpacked

# Helper classes for structured command arguments
class Command:
    def __init__(self, command_name: CommandType, args: Any):
        self.command_name = command_name
        self.args = args

class CustomerArgs:
    def __init__(self, first_name: str, last_name: str, address: str):
        self.first_name = first_name
        self.last_name = last_name
        self.address = address

class AccountArgs:
    def __init__(self, customer_id: str, account_type: AccountType):
        self.customer_id = customer_id
        self.account_type = account_type

class DepositArgs:
    def __init__(self, account_id: int, amount: Decimal):
        self.account_id = account_id
        self.amount = amount

class WithdrawArgs:
    def __init__(self, account_id: int, amount: Decimal):
        self.account_id = account_id
        self.amount = amount

class TransferArgs:
    def __init__(self, from_account_id: int, to_account_id: int, amount: Decimal):
        self.from_account_id = from_account_id
        self.to_account_id = to_account_id
        self.amount = amount

class CashCheckArgs:
    def __init__(self, account_id: int, amount: Decimal):
        self.account_id = account_id
        self.amount = amount

class GetAccountsArgs:
    def __init__(self, customer_id: str):
        self.customer_id = customer_id

class ListStatementsArgs:
    def __init__(self, account_id: int):
        self.account_id = account_id

class AdvanceTimeArgs:
    def __init__(self, delta_time: timedelta):
        self.delta_time = delta_time
