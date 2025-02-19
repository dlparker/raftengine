"""
Definitions for the API of the operations log managed by the state variants.

"""
import os
import abc
from dataclasses import dataclass, field, asdict
from typing import Union, List, Optional, Any
from enum import Enum

class RecordCode(str, Enum):
    """ String enum representing purpose of record. """

    """ Results of client command operation """
    client_command = "CLIENT_COMMAND"
    
    """ Cluster Configuration Data """
    cluster_config = "CLUSTER_CONFIG" 

    
@dataclass
class LogRec:
    index: int = field(default = 0)
    term: int = field(default = 0)
    command: str  = field(default = None, repr=False)
    result: str  = field(default = None, repr=False)
    error: bool  = field(default = False)
    code: RecordCode = field(default=RecordCode.client_command)
    local_committed: bool = field(default = False, repr=False)

    @classmethod
    def from_dict(cls, data):
        rec = cls(index=data['index'],
                  term=data['term'],
                  command=data['command'],
                  result=data['result'],
                  error=data['error'],
                  code=RecordCode(data['code']),
                  local_committed=data['local_committed'])
        return rec

class CommandLogRec(LogRec):
    pass

class ConfigLogRec(LogRec):
    code=RecordCode.cluster_config
    


# abstract class for all states
class LogAPI(metaclass=abc.ABCMeta):
    """
    Abstract base class that functions as an interface definition for 
    implmentations of Log storage that can be used by the raftengine state classes
    to create and view log records to implement the algorythm.
    """
    
    @abc.abstractmethod
    async def start(self, working_directory: os.PathLike): # pragma: no cover abstract
        raise NotImplementedError
    
    @abc.abstractmethod
    async def get_term(self) -> int:  # pragma: no cover abstract
        raise NotImplementedError
    
    @abc.abstractmethod
    async def set_term(self, value: int):  # pragma: no cover abstract
        raise NotImplementedError
    
    @abc.abstractmethod
    async def incr_term(self) -> int:  # pragma: no cover abstract
        raise NotImplementedError
    
    @abc.abstractmethod
    async def get_last_index(self) -> int:  # pragma: no cover abstract
        raise NotImplementedError

    @abc.abstractmethod
    async def get_last_term(self) -> int:  # pragma: no cover abstract
        raise NotImplementedError

    @abc.abstractmethod
    async def get_local_commit_index(self) -> int:  # pragma: no cover abstract
        raise NotImplementedError

    @abc.abstractmethod
    async def append_multi(self, entries: List[LogRec]):  # pragma: no cover abstract
        raise NotImplementedError

    @abc.abstractmethod
    async def append(self, record: LogRec):  # pragma: no cover abstract
        raise NotImplementedError

    @abc.abstractmethod
    def replace(self, entry: LogRec) -> LogRec:  # pragma: no cover abstract
        raise NotImplementedError

    @abc.abstractmethod
    def update_and_commit(self, entry: LogRec) -> LogRec:  # pragma: no cover abstract
        raise NotImplementedError

    @abc.abstractmethod
    async def read(self, index: Union[int, None] = None) -> Union[LogRec, None]:  # pragma: no cover abstract
        raise NotImplementedError


    
        



        
    
