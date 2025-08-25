import abc
from typing import Any, Optional
from dataclasses import dataclass, field

@dataclass
class SnapShot:
    index:int # This will be the index of the last committed record at snapshot time
    term:int  # This will be the term of the last committed record
    
class SnapShotToolAPI(abc.ABC):

    @abc.abstractmethod
    async def load_snapshot_chunk(self, chunk) -> None: # pragma: no cover abstract
        raise NotImplementedError

    @abc.abstractmethod
    async def get_snapshot_chunk(self, offset=0) -> (str,int,bool):# pragma: no cover abstract
        raise NotImplementedError
        
    async def apply_snapshot(self) -> SnapShot:# pragma: no cover abstract
        raise NotImplementedError

