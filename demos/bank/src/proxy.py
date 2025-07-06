from enum import StrEnum, auto
import json 
from operator import methodcaller
from typing import List, Optional, Dict, Any
from datetime import timedelta, date, datetime
from decimal import Decimal
from .datatypes import Customer, Account, AccountType
from .proxy_api import ProxyAPI


def _preprocess_for_json(obj):
    """Recursively preprocess objects to handle StrEnum before JSON serialization"""
    if isinstance(obj, AccountType):
        return {"__type__": "AccountType", "value": obj.value}
    elif isinstance(obj, dict):
        return {k: _preprocess_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_preprocess_for_json(item) for item in obj]
    elif isinstance(obj, tuple):
        return tuple(_preprocess_for_json(item) for item in obj)
    return obj


class BankJSONEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles datetime, date, timedelta, and Decimal objects"""
    
    def default(self, obj):
        if isinstance(obj, AccountType):
            return {"__type__": "AccountType", "value": obj.value}
        elif isinstance(obj, datetime):
            return {"__type__": "datetime", "value": obj.isoformat()}
        elif isinstance(obj, date):
            return {"__type__": "date", "value": obj.isoformat()}
        elif isinstance(obj, timedelta):
            return {"__type__": "timedelta", "value": obj.total_seconds()}
        elif isinstance(obj, Decimal):
            return {"__type__": "Decimal", "value": str(obj)}
        return super().default(obj)


def bank_json_decoder(dct):
    """Custom JSON decoder that reconstructs datetime, date, timedelta, and Decimal objects"""
    if "__type__" in dct:
        type_name = dct["__type__"]
        value = dct["value"]
        
        if type_name == "datetime":
            return datetime.fromisoformat(value)
        elif type_name == "date":
            return date.fromisoformat(value)
        elif type_name == "timedelta":
            return timedelta(seconds=value)
        elif type_name == "Decimal":
            return Decimal(value)
        elif type_name == "AccountType":
            return AccountType(value)
    
    return dct


def bank_json_dumps(obj):
    """Helper function that combines preprocessing and custom encoding"""
    preprocessed = _preprocess_for_json(obj)
    return json.dumps(preprocessed, cls=BankJSONEncoder)


def bank_json_loads(json_str):
    """Helper function for decoding with custom decoder"""
    return json.loads(json_str, object_hook=bank_json_decoder)


class CommandType(StrEnum):

    CREATE_CUSTOMER = auto()
    CREATE_ACCOUNT = auto()
    DEPOSIT = auto()
    WITHDRAW = auto()
    TRANSFER = auto()
    CASH_CHECK = auto()
    LIST_ACCOUNTS = auto()
    GET_ACCOUNTS = auto()
    LIST_STATEMENTS = auto()
    ADVANCE_TIME  = auto()

class ServerProxy(ProxyAPI):

    def __init__(self, server_wrapper: 'ServerWrapper') -> None:
        self.server_wrapper = server_wrapper
        
    async def create_customer(self, first_name: str, last_name: str, address: str) -> Customer:
        args = locals()
        del args['self']
        return await self.server_wrapper.do_command(CommandType.CREATE_CUSTOMER, args)

    async def create_account(self, customer_id: str, account_type: AccountType) -> Account:
        args = locals()
        del args['self']
        return await self.server_wrapper.do_command(CommandType.CREATE_ACCOUNT, args)

    async def deposit(self, account_id: int, amount: Decimal) -> Decimal:
        args = locals()
        del args['self']
        return await self.server_wrapper.do_command(CommandType.DEPOSIT, args)
    
    async def withdraw(self, account_id: int, amount: Decimal) -> Decimal:
        args = locals()
        del args['self']
        return await self.server_wrapper.do_command(CommandType.WITHDRAW, args)
    
    async def transfer(self, from_account_id: int, to_account_id: int, amount: Decimal) -> Optional[Dict[str, Decimal]]:
        args = locals()
        del args['self']
        return await self.server_wrapper.do_command(CommandType.TRANSFER, args)

    async def cash_check(self, account_id: int, amount: Decimal) -> Decimal:
        args = locals()
        del args['self']
        return await self.server_wrapper.do_command(CommandType.CASH_CHECK, args)
    
    async def list_accounts(self) -> List[Account]:
        args = locals()
        del args['self']
        return await self.server_wrapper.do_command(CommandType.LIST_ACCOUNTS, args)
    
    async def get_accounts(self, customer_id: str) -> List[int]:
        args = locals()
        del args['self']
        return await self.server_wrapper.do_command(CommandType.GET_ACCOUNTS, args)
    
    async def list_statements(self, account_id: int) -> List[date]:
        args = locals()
        del args['self']
        return await self.server_wrapper.do_command(CommandType.LIST_STATEMENTS, args)
    
    async def advance_time(self, delta_time: timedelta) -> None:
        args = locals()
        del args['self']
        return await self.server_wrapper.do_command(CommandType.ADVANCE_TIME, args)

    
class ServerWrapper:

    def __init__(self, server: Any) -> None:
        self.server = server
        
    async def do_command(self, command_name: CommandType, argsdict: Dict[str, Any]) -> Any:
        send_data = dict(command_name=command_name, args=argsdict)
        # pretend this is a call to raft library "run_command" method
        # so that command gets logged, replicated, committed and then applied by calling us back
        result = await self.fake_raft_replicate(bank_json_dumps(send_data))
        return result

    async def fake_raft_replicate(self, data):
        # this is sort of a simulation of receiving a raft log replication "apply" operation
        # once a command has been "committed". 
        request = bank_json_loads(data)
        result = await self.really_do_command(request['command_name'], request['args'])
        return result
    
    async def really_do_command(self, command_name: CommandType, argsdict: Dict[str, Any]) -> Any:
        callable_method = methodcaller(command_name, **argsdict)
        res = await callable_method(self.server)
        return res
        
    
    



