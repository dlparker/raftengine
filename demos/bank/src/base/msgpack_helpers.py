import msgpack
from typing import Any
from datetime import timedelta, date, datetime
from decimal import Decimal
from dataclasses import asdict, is_dataclass
from base.datatypes import AccountType, CommandType, Customer, Account, Transaction, Statement


def _preprocess_for_msgpack(obj):
    """Recursively preprocess objects to handle StrEnum and dataclasses before msgpack serialization"""
    if isinstance(obj, (AccountType, CommandType)):
        return {"__type__": type(obj).__name__, "value": obj.value}
    elif is_dataclass(obj):
        return {"__type__": type(obj).__name__, "value": asdict(obj)}
    elif isinstance(obj, dict):
        return {k: _preprocess_for_msgpack(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_preprocess_for_msgpack(item) for item in obj]
    elif isinstance(obj, tuple):
        return tuple(_preprocess_for_msgpack(item) for item in obj)
    return obj


def _msgpack_encoder(obj):
    """Custom encoder for msgpack that handles datetime, date, timedelta, and Decimal objects"""
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
    return obj


def _msgpack_decoder(obj):
    """Custom decoder that reconstructs datetime, date, timedelta, Decimal, and dataclass objects"""
    if isinstance(obj, dict) and "__type__" in obj:
        type_name = obj["__type__"]
        value = obj["value"]
        
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
    
    return obj


def bank_msgpack_dumps(obj: Any) -> bytes:
    """Helper function that combines preprocessing and custom encoding"""
    preprocessed = _preprocess_for_msgpack(obj)
    return msgpack.packb(preprocessed, default=_msgpack_encoder)


def bank_msgpack_loads(data: bytes) -> Any:
    """Helper function for decoding with custom decoder"""
    return msgpack.unpackb(data, object_hook=_msgpack_decoder, raw=False)


class BankPacker:
    """Custom packer/unpacker for aiozmq.rpc that handles banking dataclasses"""
    
    def packb(self, obj):
        return bank_msgpack_dumps(obj)
    
    def unpackb(self, data):
        return bank_msgpack_loads(data)


def get_bank_translation_table():
    """Get translation table for aiozmq.rpc custom serialization"""
    return {
        0: (Customer, 
            lambda obj: bank_msgpack_dumps(obj),
            lambda data: bank_msgpack_loads(data)),
        1: (Account, 
            lambda obj: bank_msgpack_dumps(obj),
            lambda data: bank_msgpack_loads(data)),
        2: (Transaction, 
            lambda obj: bank_msgpack_dumps(obj),
            lambda data: bank_msgpack_loads(data)),
        3: (Statement, 
            lambda obj: bank_msgpack_dumps(obj),
            lambda data: bank_msgpack_loads(data)),
        4: (AccountType, 
            lambda obj: bank_msgpack_dumps(obj),
            lambda data: bank_msgpack_loads(data)),
        5: (CommandType, 
            lambda obj: bank_msgpack_dumps(obj),
            lambda data: bank_msgpack_loads(data)),
        6: (Decimal, 
            lambda obj: bank_msgpack_dumps(obj),
            lambda data: bank_msgpack_loads(data)),
        7: (datetime, 
            lambda obj: bank_msgpack_dumps(obj),
            lambda data: bank_msgpack_loads(data)),
        8: (date, 
            lambda obj: bank_msgpack_dumps(obj),
            lambda data: bank_msgpack_loads(data)),
        9: (timedelta, 
            lambda obj: bank_msgpack_dumps(obj),
            lambda data: bank_msgpack_loads(data)),
    }