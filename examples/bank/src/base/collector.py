from typing import List, Optional, Dict, Any, Union
import logging
from datetime import timedelta, date, datetime
from decimal import Decimal
from base.datatypes import Customer, Account, AccountType, CommandType
from base.proxy import TellerProxyAPI
import msgspec
import json
from raftengine.deck.log_control import LogController
logger = LogController.get_controller().add_logger("base.Collector",
                                                 "The component that coverts method calls that the Teller"\
                                                 " object expects into serialize commands for raft_command calls")

# Custom encoder/decoder functions for msgspec
def enc_hook(obj):
    """Custom encoder for types that msgspec doesn't natively support"""
    if isinstance(obj, Decimal):
        return {"__decimal__": str(obj)}
    elif isinstance(obj, timedelta):
        return {"__timedelta__": obj.total_seconds()}
    elif isinstance(obj, date):
        return {"__date__": obj.isoformat()}
    elif isinstance(obj, (AccountType, CommandType)):
        return obj.value
    raise NotImplementedError(f"Objects of type {type(obj)} are not supported")

def dec_hook(type_, obj):
    """Custom decoder for reconstructing special types"""
    if isinstance(obj, dict):
        if "__decimal__" in obj:
            return Decimal(obj["__decimal__"])
        elif "__timedelta__" in obj:
            return timedelta(seconds=obj["__timedelta__"])
        elif "__date__" in obj:
            return date.fromisoformat(obj["__date__"])
    return obj


class Collector(TellerProxyAPI):

    def __init__(self, pipe):
        self.pipe = pipe

    async def create_customer(self, first_name: str, last_name: str, address: str) -> Customer:
        command = Command(command_name=CommandType.CREATE_CUSTOMER,
                          args=CustomerArgs(first_name=first_name, last_name=last_name, address=address))
        return await self.build_command(command, Customer)

    async def create_account(self, customer_id: int, account_type: AccountType) -> Account:
        command = Command(command_name=CommandType.CREATE_ACCOUNT,
                          args=AccountArgs(customer_id=customer_id, account_type=account_type))
        return await self.build_command(command, Account)

    async def deposit(self, account_id: int, amount: Decimal) -> Decimal:
        command = Command(command_name=CommandType.DEPOSIT,
                          args=DepositArgs(account_id=account_id, amount=amount))
        return await self.build_command(command, Decimal)

    async def withdraw(self, account_id: int, amount: Decimal) -> Decimal:
        command = Command(command_name=CommandType.WITHDRAW,
                          args=WithdrawArgs(account_id=account_id, amount=amount))
        return await self.build_command(command, Decimal)

    async def transfer(self, from_account_id: int, to_account_id: int, amount: Decimal) -> Optional[Dict[str, Decimal]]:
        command = Command(command_name=CommandType.TRANSFER,
                          args=TransferArgs(from_account_id=from_account_id,
                                            to_account_id=to_account_id, amount=amount))
        return await self.build_command(command, Optional[Dict[str, Decimal]])

    async def cash_check(self, account_id: int, amount: Decimal) -> Decimal:
        command = Command(command_name=CommandType.CASH_CHECK,
                          args=CashCheckArgs(account_id=account_id, amount=amount))
        return await self.build_command(command, Decimal)

    async def list_accounts(self, offset: int = 0, limit: int = 100) -> List[Account]:
        command = Command(command_name=CommandType.LIST_ACCOUNTS,
                          args=ListAccountsArgs(offset=offset, limit=limit))
        return await self.build_command(command, List[Account])
    
    async def list_customers(self, offset: int = 0, limit: int = 100) -> List[Customer]:
        command = Command(command_name=CommandType.LIST_CUSTOMERS,
                          args=ListCustomersArgs(offset=offset, limit=limit))
        return await self.build_command(command, List[Customer])

    async def get_accounts(self, customer_id: int) -> List[int]:
        command = Command(command_name=CommandType.GET_ACCOUNTS,
                          args=GetAccountsArgs(customer_id=customer_id))
        return await self.build_command(command, List[int])

    async def list_statements(self, account_id: int) -> List[date]:
        command = Command(command_name=CommandType.LIST_STATEMENTS,
                          args=ListStatementsArgs(account_id=account_id))
        return await self.build_command(command, List[date])

    async def advance_time(self, delta_time: timedelta) -> None:
        command = Command(command_name=CommandType.ADVANCE_TIME,
                          args=AdvanceTimeArgs(delta_time=delta_time))
        await self.build_command(command, None)

    async def get_customer_count(self) -> int:
        command = Command(command_name=CommandType.GET_CUSTOMER_COUNT,
                          args=None)
        return await self.build_command(command, int)

    async def get_account_count(self) -> int:
        command = Command(command_name=CommandType.GET_ACCOUNT_COUNT,
                          args=None)
        return await self.build_command(command, int)

    async def build_command(self, command: 'Command', return_type: Any) -> Any:
        request = msgspec.json.encode(command, enc_hook=enc_hook).decode('utf-8')
        response = await self.pipe.run_command(request)
        # For complex return types, we'll use json module and then reconstruct
        # This is because msgspec can't easily decode arbitrary return types with custom hooks
        response_data = json.loads(response)
        # Handle special decoding manually
        return self._decode_response(response_data, return_type)
    
    def _decode_response(self, data: Any, expected_type: Any) -> Any:
        """Custom decoder for response data"""
        if data is None:
            return None
        elif isinstance(data, dict):
            # Handle special encoded types
            if "__decimal__" in data:
                return Decimal(data["__decimal__"])
            elif "__timedelta__" in data:
                return timedelta(seconds=data["__timedelta__"])
            elif "__date__" in data:
                return date.fromisoformat(data["__date__"])
            # Handle complex objects like Customer, Account
            elif "first_name" in data and "last_name" in data:  # Customer
                # For Customer, the accounts field should be a list of integers (account IDs)
                # not a list of Account objects as expected by from_dict
                # So let's create a Customer directly from the serialized data
                return Customer(
                    cust_id=data["cust_id"],
                    first_name=data["first_name"],
                    last_name=data["last_name"],
                    address=data["address"],
                    accounts=data["accounts"],  # This should be a list of integers
                    create_time=datetime.fromisoformat(data["create_time"]) if isinstance(data["create_time"], str) else data["create_time"],
                    update_time=datetime.fromisoformat(data["update_time"]) if isinstance(data["update_time"], str) else data["update_time"]
                )
            elif "account_type" in data and "balance" in data:  # Account
                return Account.from_dict(data)
            else:
                # Handle dictionaries with special values
                return {k: self._decode_response(v, None) for k, v in data.items()}
        elif isinstance(data, list):
            # Handle lists of objects
            return [self._decode_response(item, None) for item in data]
        else:
            return data

# Helper classes for structured command arguments using msgspec
class CustomerArgs(msgspec.Struct):
    first_name: str
    last_name: str
    address: str

class AccountArgs(msgspec.Struct):
    customer_id: int
    account_type: AccountType

class DepositArgs(msgspec.Struct):
    account_id: int
    amount: Decimal

class WithdrawArgs(msgspec.Struct):
    account_id: int
    amount: Decimal

class TransferArgs(msgspec.Struct):
    from_account_id: int
    to_account_id: int
    amount: Decimal

class CashCheckArgs(msgspec.Struct):
    account_id: int
    amount: Decimal

class GetAccountsArgs(msgspec.Struct):
    customer_id: int

class ListStatementsArgs(msgspec.Struct):
    account_id: int

class AdvanceTimeArgs(msgspec.Struct):
    delta_time: timedelta

class ListAccountsArgs(msgspec.Struct):
    offset: int = 0
    limit: int = 100

class ListCustomersArgs(msgspec.Struct):
    offset: int = 0
    limit: int = 100

class Command(msgspec.Struct):
    command_name: CommandType
    args: Optional[Union[
        CustomerArgs, AccountArgs, DepositArgs, WithdrawArgs, TransferArgs,
        CashCheckArgs, GetAccountsArgs, ListStatementsArgs, AdvanceTimeArgs,
        ListAccountsArgs, ListCustomersArgs
    ]] = None

