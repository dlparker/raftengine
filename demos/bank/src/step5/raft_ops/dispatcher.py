import logging
from operator import methodcaller
from typing import Any
from base.json_helpers import bank_json_loads, bank_json_dumps
logger = logging.getLogger(__name__)

class Dispatcher:

    def __init__(self, operations):
        self.operations = operations

    async def run_command(self, request) -> Any:
        try:
            logger.debug(f"Dispatcher processing request: {request}")
            rdict = bank_json_loads(request)
            logger.debug(f"Parsed command: {rdict}")
            
            command_name = rdict['command_name']
            args = rdict['args']
            
            # Validate command_name is string
            if not isinstance(command_name, str):
                raise ValueError(f"command_name must be string, got {type(command_name)}: {command_name}")
            
            # Validate method exists
            if not hasattr(self.operations, command_name):
                available_methods = [name for name in dir(self.operations) if not name.startswith('_') and callable(getattr(self.operations, name))]
                raise AttributeError(f"Operations class has no method '{command_name}'. Available methods: {available_methods}")
            
            logger.debug(f"Calling {command_name} with args: {args}")
            callable_method = methodcaller(command_name, **args)
            res = await callable_method(self.operations)
            logger.debug(f"Command {command_name} completed successfully: {type(res)}")
            
            # in this setup, we need to serialize result, normally you wouldn't
            serialized_result = bank_json_dumps(res)
            logger.debug(f"Serialized result length: {len(serialized_result)} chars")
            return serialized_result
            
        except Exception as e:
            logger.error(f"Dispatcher.run_command failed: {e}")
            logger.error(f"Request was: {request}")
            logger.error(f"Exception type: {type(e).__name__}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            raise  # Re-raise so Pilot can handle it properly
        
