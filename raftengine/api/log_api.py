"""
Definitions for the API of the operations log managed by the state variants.

"""
import os
import abc
from dataclasses import dataclass, field, asdict
from typing import Union, List, Optional, Any
from enum import Enum
from raftengine.api.types import ClusterConfig
from raftengine.api.snapshot_api import SnapShot

class RecordCode(str, Enum):
    """ String enum representing purpose of record. """

    """ Record leader saves to start a term, effectively committing all 
         previous recurds because of the usual commit logic """
    term_start = "TERM_START"
    
    """ Results of client command operation """
    client_command = "CLIENT_COMMAND"
    
    """ Cluster Configuration Data """
    cluster_config = "CLUSTER_CONFIG" 

    
@dataclass
class LogRec:
    index: int = field(default = 0)
    term: int = field(default = 0)
    command: str = field(default = None, repr=False)
    result: str = field(default = None, repr=False)
    error: bool = field(default = False)
    code: RecordCode = field(default=RecordCode.client_command)
    serial: int = field(default = None, repr=False)
    leader_id: str = field(default = None, repr=False)
    committed: bool = field(default = False)
    applied: bool =  field(default = False)

    @classmethod
    def from_dict(cls, data):
        copy_of = dict(data)
        if not isinstance(data['code'], RecordCode):
            copy_of['code'] = RecordCode(data['code'])
        rec = cls(**copy_of)
        return rec

class CommandLogRec(LogRec):
    pass

class ConfigLogRec(LogRec):
    code=RecordCode.cluster_config
    


# abstract class for all roles
class LogAPI(abc.ABC):
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
    async def get_voted_for(self) -> int:  # pragma: no cover abstract
        raise NotImplementedError
    
    @abc.abstractmethod
    async def set_voted_for(self, value: int):  # pragma: no cover abstract
        raise NotImplementedError
    
    @abc.abstractmethod
    async def get_last_index(self) -> int:  # pragma: no cover abstract
        raise NotImplementedError

    @abc.abstractmethod
    async def get_first_index(self) -> int:  # pragma: no cover abstract
        raise NotImplementedError

    @abc.abstractmethod
    async def get_last_term(self) -> int:  # pragma: no cover abstract
        raise NotImplementedError

    @abc.abstractmethod
    async def get_commit_index(self) -> int:  # pragma: no cover abstract
        raise NotImplementedError

    @abc.abstractmethod
    async def get_applied_index(self) -> int:  # pragma: no cover abstract
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
    def update_and_apply(self, entry: LogRec) -> LogRec:  # pragma: no cover abstract
        raise NotImplementedError

    @abc.abstractmethod
    async def read(self, index: Union[int, None] = None) -> Union[LogRec, None]:  # pragma: no cover abstract
        raise NotImplementedError

    @abc.abstractmethod
    async def delete_all_from(self, index: int) -> LogRec:  # pragma: no cover abstract
        raise NotImplementedError

    @abc.abstractmethod
    async def save_cluster_config(self, config: ClusterConfig) -> None:  # pragma: no cover abstract
        raise NotImplementedError

    @abc.abstractmethod
    async def get_cluster_config(self) -> Optional[ClusterConfig]:  # pragma: no cover abstract
        raise NotImplementedError

    @abc.abstractmethod
    async def install_snapshot(self, snapshot:SnapShot) -> None: # pragma: no cover abstract
        raise NotImplementedError

        



        
    
