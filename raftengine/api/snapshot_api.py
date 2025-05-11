import abc
from typing import Any, Optional
from dataclasses import dataclass

    
class SnapshotToolAPI(abc.ABC):

    @abc.abstractmethod
    async def load_snapshot_chunk(self, snapshot, chunk) -> None: # pragma: no cover abstract
        raise NotImplementedError

    @abc.abstractmethod
    async def get_snapshot_chunk(self, snapshot, offset=0) -> (str,int,bool):# pragma: no cover abstract
        raise NotImplementedError
        

@dataclass
class SnapShot:
    last_index:int
    last_term:int
    tool:SnapshotToolAPI
