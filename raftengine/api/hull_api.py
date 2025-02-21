import abc
from typing import List, Any
from raftengine.api.log_api import LogAPI


class HullAPI(metaclass=abc.ABCMeta):
    """
    """
    @abc.abstractmethod
    async def start(self):
        raise NotImplementedError
    
    @abc.abstractmethod
    async def on_message(self, in_message):
        raise NotImplementedError

    # Part of API
    async def run_command(self, command, timeout):
        raise NotImplementedError
