import logging
from typing import Any
from operator import methodcaller
import traceback
import jsonpickle
from raftengine.deck.log_control import LogController
from base.datatypes import CommandType, Customer, Account, AccountType
from base.collector import Command 

logger = LogController.get_controller().add_logger("base.Dispatcher",
                                                 "The component that coverts serialized method calls"\
                                                 " into actual calls to the he Teller object")

class Dispatcher:
    def __init__(self, teller):
        self.teller = teller
        # Configure jsonpickle for clean output
        jsonpickle.set_encoder_options('json', indent=2, sort_keys=True)

    async def run_command(self, request: str) -> str:
        result = None
        try:
            # Deserialize jsonpickle-encoded command
            command = jsonpickle.decode(request)
            if not isinstance(command, Command):
                msg = f"Invalid command format: expected Command, got {type(command)}"
                logger.error(msg)
                raise ValueError(msg)

            command_name = command.command_name.value  # Extract string value from CommandType
            logger.debug('dispatching command %s', command_name)
            args = command.args

            # Validate method exists
            if not hasattr(self.teller, command_name):
                msg = f"Teller class has no method '{command_name}'"
                logger.error(msg)
                raise AttributeError(msg)

            # Convert args to dictionary for method call
            if args is None or args == {}:
                kwargs = {}
            else:
                kwargs = args.__dict__

            # Call teller method
            callable_method = methodcaller(command_name, **kwargs)
            result = await callable_method(self.teller)
            logger.debug("command %s result sending")
            serialized_result = jsonpickle.encode(result)
            return serialized_result

        except Exception as e:
            error = traceback.format_exc()
            logger.error("error in command processing %s", error)
            serialized_result = jsonpickle.encode(result)
            return serialized_result
