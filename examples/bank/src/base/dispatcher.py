import logging
from typing import Any
from operator import methodcaller
import jsonpickle
from base.datatypes import CommandType, Customer, Account, AccountType
from base.collector import Command 

logger = logging.getLogger(__name__)

class Dispatcher:
    def __init__(self, teller):
        self.teller = teller
        # Configure jsonpickle for clean output
        jsonpickle.set_encoder_options('json', indent=2, sort_keys=True)

    async def run_command(self, request: str) -> str:
        try:
            # Deserialize jsonpickle-encoded command
            command = jsonpickle.decode(request)
            if not isinstance(command, Command):
                logger.error(f"Expected Command, got {type(command)}")
                raise ValueError(f"Invalid command format: expected Command, got {type(command)}")

            command_name = command.command_name.value  # Extract string value from CommandType
            args = command.args

            # Validate method exists
            if not hasattr(self.teller, command_name):
                logger.error(f"Teller class has no method '{command_name}'")
                raise AttributeError(f"Teller class has no method '{command_name}'")

            # Convert args to dictionary for method call
            if args is None or args == {}:
                kwargs = {}
            else:
                kwargs = args.__dict__

            # Call teller method
            callable_method = methodcaller(command_name, **kwargs)
            result = await callable_method(self.teller)
            serialized_result = jsonpickle.encode(result)
            return serialized_result

        except Exception as e:
            # Return error in CommandResult
            command_result = CommandResult(
                command=command_name if 'command_name' in locals() else "unknown",
                error=str(e),
                timeout_expired=False
            )
            serialized_result = jsonpickle.encode(command_result)
            return serialized_result
