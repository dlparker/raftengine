import logging
import json
from typing import Any
from decimal import Decimal, ROUND_HALF_UP
from operator import methodcaller
from datetime import timedelta
logger = logging.getLogger(__name__)


class Dispatcher:

    def __init__(self, teller):
        self.teller = teller

    async def run_command(self, request) -> Any:
        try:
            logger.debug(f"Dispatcher processing request: {request}")
            rdict = json.loads(request)
            logger.debug(f"Parsed command: {rdict}")
            
            command_name = rdict['command_name']
            kwargs = rdict['args']

            # Validate method exists
            if not hasattr(self.teller, command_name):
                raise AttributeError(f"Teller class has no method '{command_name}'")
            if command_name in ['deposit', 'withdraw', 'transfer', 'cash_check']:
                kwargs['amount'] = Decimal(str(kwargs['amount'])).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            if command_name == 'advance_time':
                kwargs['delta_time'] = timedelta(seconds=kwargs['delta_time'])
            
            logger.debug(f"Calling {command_name} with args: {kwargs}")
            callable_method = methodcaller(command_name, **kwargs)
            res = await callable_method(self.teller)
            logger.debug(f"Command {command_name} completed successfully: {type(res)}")
            
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
                
            logger.debug(f"Serialized result length: {len(serialized_result)} chars")
            return serialized_result
            
        except Exception as e:
            logger.error(f"Dispatcher.run_command failed: {e}")
            logger.error(f"Request was: {request}")
            logger.error(f"Exception type: {type(e).__name__}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            raise  # Re-raise so Pilot can handle it properly
        
