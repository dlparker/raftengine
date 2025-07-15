"""
This version of the Dispatcher uses the built in python json module and custom actions
to implement the serialization of the TellerProxyAPI. It is a pain, and error prone.
It is provided here for illustration only. All the running code uses the json_pickle
version in dispatcher.py. Each version needs a matching collector.

"""
import logging
import json
from typing import Any
from decimal import Decimal, ROUND_HALF_UP
from operator import methodcaller
from datetime import timedelta


class Dispatcher:

    def __init__(self, teller):
        self.teller = teller

    async def run_command(self, request) -> Any:
        rdict = json.loads(request)

        command_name = rdict['command_name']
        kwargs = rdict['args']

        # Validate method exists
        if not hasattr(self.teller, command_name):
            raise AttributeError(f"Teller class has no method '{command_name}'")
        if command_name in ['deposit', 'withdraw', 'transfer', 'cash_check']:
            kwargs['amount'] = Decimal(str(kwargs['amount'])).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        if command_name == 'advance_time':
            kwargs['delta_time'] = timedelta(seconds=kwargs['delta_time'])

        callable_method = methodcaller(command_name, **kwargs)
        res = await callable_method(self.teller)

        # in this setup, we need to serialize result, normally you wouldn't
        if isinstance(res, Decimal):
            serialized_result  = json.dumps(dict(result=float(res)))
        elif isinstance(res, dict):
            new_res = dict()
            for key in res:
                if isinstance(res[key], Decimal):
                    new_res[key] = float(res[key])
                else:
                    new_res[key] = res[key]
            serialized_result = json.dumps(dict(result=new_res), default=lambda o:o.to_dict())
        else:
            serialized_result = json.dumps(dict(result=res), default=lambda o:o.to_dict())

        return serialized_result
            
        
