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

    """ When leader starts up, marks start of term with this """
    no_op = "NO_OP"

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
    code: RecordCode = field(default=RecordCode.client_command)
    leader_committed: bool = field(default = False, repr=False)
    local_committed: bool = field(default = False, repr=False)

    @classmethod
    def from_dict(cls, data):
        rec = cls(index=data['index'],
                  term=data['term'],
                  command=data['command'],
                  result=data['result'],
                  code=RecordCode(data['code']),
                  leader_committed=data['leader_committed'],
                  local_committed=data['local_committed'])
        return rec
    
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
    async def append(self, entries: List[LogRec]):  # pragma: no cover abstract
        raise NotImplementedError

    @abc.abstractmethod
    def replace_or_append(self, entry: LogRec) -> LogRec:  # pragma: no cover abstract
        raise NotImplementedError

    @abc.abstractmethod
    async def read(self, index: Union[int, None] = None) -> Union[LogRec, None]:  # pragma: no cover abstract
        raise NotImplementedError

    @abc.abstractmethod
    async def get_last_index(self) -> int:  # pragma: no cover abstract
        raise NotImplementedError

    @abc.abstractmethod
    async def get_last_term(self) -> int:  # pragma: no cover abstract
        raise NotImplementedError

    
        



        
    
