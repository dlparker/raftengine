"""
These operations are triggered by RPCs to a server and performed locally on that
server instead of being replicated via Raft. Mostly operations relevant to the
server process, though they can also be operations on the Teller data as long
as there is no risky of a dirty read, or if that risk is tollerable. Querying
for a statement from a past month, for example. Statements never change after
creation, and if the requested one is unavailable because it is being prepared,
then the application logic should tollerate that.
"""
from typing import List, Optional, Dict, Any
import os
import json
import logging
import traceback
from operator import methodcaller
import jsonpickle
from enum import StrEnum, auto
logger = logging.getLogger(__name__)


class LocalCommandType(StrEnum):
    """Command types for the local_command function 
    
    These values must exactly match the method names on the LocalFunctions class
    that are to be executed as remote commands through the proxy layer.
    """
    GET_PID = auto()

    # If raft timed operations have not started this will start them    
    START_RAFT = auto()

    # Will stop Raft ops then whole server process
    STOP_SERVER = auto()

    # Will cause target server to try to take power.
    # Bad idea in production, useful in testing, running
    # demos, etc.
    START_CAMPAIGN = auto()  

class LocalCommand:

    def __init__(self, command_name: LocalCommandType, args: Any):
        self.command_name = command_name
        self.args = args

class LocalResult:

    def __init__(self, result, error=None):
        self.result = result
        self.error = error

class LocalCollector:

    def __init__(self, pipe):
        self.pipe = pipe
        # Configure jsonpickle for clean output
        jsonpickle.set_encoder_options('json', indent=2, sort_keys=True)

    async def get_pid(self) -> int:
        command = LocalCommand(command_name=LocalCommandType.GET_PID, args=None)
        return await self.build_command(command)

    async def start_raft(self) -> int:
        command = LocalCommand(command_name=LocalCommandType.START_RAFT, args=None)
        return await self.build_command(command)

    async def stop_server(self) -> int:
        command = LocalCommand(command_name=LocalCommandType.STOP_SERVER, args=None)
        return await self.build_command(command)

    async def start_campaign(self) -> int:
        command = LocalCommand(command_name=LocalCommandType.START_CAMPAIGN, args=None)
        return await self.build_command(command)
    
    async def build_command(self, command: 'Command') -> Any:
        # Serialize command object to JSON
        request = jsonpickle.encode(command)
        response = await self.pipe.local_command(request)
        unpacked = jsonpickle.decode(response)

        # If jsonpickle fails to deserialize LocalResult, handle it manually
        if not isinstance(unpacked, str):
            result = unpacked
        else:
            json_data = json.loads(unpacked)
            if "py/object" in json_data:
                del json_data["py/object"]
            result = LocalResult(**json_data)
        if result.error:
            raise Exception(f'Local command on server return error {result.error}')
        return result.result

class LocalDispatcher:
    
    def __init__(self, local_ops):
        self.local_ops = local_ops
        # Configure jsonpickle for clean output
        jsonpickle.set_encoder_options('json', indent=2, sort_keys=True)

    async def local_command(self, request: str) -> str:
        try:
            # Deserialize jsonpickle-encoded command
            command = jsonpickle.decode(request)
            if not isinstance(command, LocalCommand):
                msg = f"Invalid command format: expected LocalCommand, got {type(command)}"
                logger.error(msg)
                raise ValueError(msg)

            command_name = command.command_name.value  # Extract string value from CommandType
            args = command.args

            # Validate method exists
            if not hasattr(self.local_ops, command_name):
                msg = f"LocalOps class has no method '{command_name}'"
                logger.error(msg)
                raise AttributeError(msg)

            # Convert args to dictionary for method call
            if args is None or args == {}:
                kwargs = {}
            else:
                kwargs = args.__dict__

            # Call teller method
            callable_method = methodcaller(command_name, **kwargs)
            op_result = await callable_method(self.local_ops)
            result = LocalResult(result=op_result)
            serialized_result = jsonpickle.encode(result)
            return serialized_result
        except Exception as e:
            result = LocalResult(result=None, error=traceback.format_exc())
            serialized_result = jsonpickle.encode(result)
            return serialized_result


 
    
