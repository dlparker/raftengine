import logging
from typing import Any
from operator import methodcaller
import traceback
import msgspec
import json
from datetime import timedelta, date
from decimal import Decimal
from raftengine.deck.log_control import LogController
from base.datatypes import CommandType, Customer, Account, AccountType
from base.collector import Command, enc_hook 

logger = LogController.get_controller().add_logger("base.Dispatcher",
                                                 "The component that coverts serialized method calls"\
                                                 " into actual calls to the he Teller object")

def decode_request_data(data):
    """Custom decoder for request data with special types"""
    if isinstance(data, dict):
        # Handle special encoded types
        if "__decimal__" in data:
            return Decimal(data["__decimal__"])
        elif "__timedelta__" in data:
            return timedelta(seconds=data["__timedelta__"])
        elif "__date__" in data:
            return date.fromisoformat(data["__date__"])
        else:
            # Recursively decode nested structures
            decoded = {}
            for k, v in data.items():
                # Special handling for amount fields which should be Decimal
                if k == "amount" and isinstance(v, str):
                    try:
                        decoded[k] = Decimal(v)
                    except:
                        decoded[k] = decode_request_data(v)
                elif k == "delta_time":
                    # Handle timedelta serialized as different formats
                    if isinstance(v, (int, float)):
                        decoded[k] = timedelta(seconds=v)
                    elif isinstance(v, str):
                        # msgspec Struct serializes timedelta as ISO8601 duration string "P1D"
                        # Convert it to seconds and create timedelta
                        if v.startswith('P') and 'D' in v:
                            days = int(v[1:v.index('D')])
                            decoded[k] = timedelta(days=days)
                        else:
                            # Fallback: try to parse as seconds
                            try:
                                decoded[k] = timedelta(seconds=float(v))
                            except:
                                decoded[k] = decode_request_data(v)
                    else:
                        decoded[k] = decode_request_data(v)
                else:
                    decoded[k] = decode_request_data(v)
            return decoded
    elif isinstance(data, list):
        return [decode_request_data(item) for item in data]
    else:
        return data

def dec_hook(type_, obj):
    """Custom decoder hook for msgspec MessagePack decoding"""
    if isinstance(obj, dict):
        if "__decimal__" in obj:
            return Decimal(obj["__decimal__"])
        elif "__timedelta__" in obj:
            return timedelta(seconds=obj["__timedelta__"])
        elif "__date__" in obj:
            return date.fromisoformat(obj["__date__"])
    return obj

class Dispatcher:
    def __init__(self, teller):
        self.teller = teller

    async def run_command(self, request: str) -> str:
        result = None
        try:
            # First parse as JSON to handle custom types manually
            request_data = msgspec.json.decode(request)
            decoded_data = decode_request_data(request_data)
            
            # Reconstruct Command object manually since msgspec.json.decode doesn't work well with custom hooks
            command_name_str = decoded_data['command_name']
            command_name = CommandType(command_name_str)
            args_data = decoded_data.get('args')
            
            logger.debug('dispatching command %s', command_name.value)
            
            # Validate method exists
            if not hasattr(self.teller, command_name.value):
                msg = f"Teller class has no method '{command_name.value}'"
                logger.error(msg)
                raise AttributeError(msg)

            # Convert args to dictionary for method call
            if args_data is None:
                kwargs = {}
            else:
                kwargs = args_data

            # Call teller method
            callable_method = methodcaller(command_name.value, **kwargs)
            result = await callable_method(self.teller)
            logger.debug("command %s result sending")
            
            # Serialize result using msgspec with custom encoder
            serialized_result = msgspec.json.encode(result, enc_hook=enc_hook).decode('utf-8')
            return serialized_result

        except Exception as e:
            error = traceback.format_exc()
            logger.error("error in command processing %s", error)
            # Serialize error result
            serialized_result = msgspec.json.encode(result, enc_hook=enc_hook).decode('utf-8')
            return serialized_result

