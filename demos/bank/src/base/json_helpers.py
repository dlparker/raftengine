import json
from typing import Any
from datetime import timedelta, date, datetime
from decimal import Decimal
from dataclasses import asdict, is_dataclass
from src.base.datatypes import AccountType, CommandType, Customer, Account, Transaction, Statement


def _preprocess_for_json(obj):
    """Recursively preprocess objects to handle StrEnum and dataclasses before JSON serialization"""
    if isinstance(obj, (AccountType, CommandType)):
        return {"__type__": type(obj).__name__, "value": obj.value}
    elif is_dataclass(obj):
        return {"__type__": type(obj).__name__, "value": asdict(obj)}
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
        if isinstance(obj, (AccountType, CommandType)):
            return {"__type__": type(obj).__name__, "value": obj.value}
        elif is_dataclass(obj):
            return {"__type__": type(obj).__name__, "value": asdict(obj)}
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
    """Custom JSON decoder that reconstructs datetime, date, timedelta, Decimal, and dataclass objects"""
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
        elif type_name == "CommandType":
            return CommandType(value)
        elif type_name == "Customer":
            return Customer(**value)
        elif type_name == "Account":
            # Handle AccountType enum conversion
            if 'account_type' in value and isinstance(value['account_type'], str):
                value['account_type'] = AccountType(value['account_type'])
            return Account(**value)
        elif type_name == "Transaction":
            return Transaction(**value)
        elif type_name == "Statement":
            return Statement(**value)
    
    return dct


def bank_json_dumps(obj: Any) -> str:
    """Helper function that combines preprocessing and custom encoding"""
    preprocessed = _preprocess_for_json(obj)
    return json.dumps(preprocessed, cls=BankJSONEncoder)


def bank_json_loads(json_str: str) -> Any:
    """Helper function for decoding with custom decoder"""
    return json.loads(json_str, object_hook=bank_json_decoder)