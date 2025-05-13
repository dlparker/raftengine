import abc
from typing import Any, Optional
from dataclasses import dataclass, field

    
class SnapShotToolAPI(abc.ABC):

    @abc.abstractmethod
    async def load_snapshot_chunk(self, chunk) -> None: # pragma: no cover abstract
        raise NotImplementedError

    @abc.abstractmethod
    async def get_snapshot_chunk(self, offset=0) -> (str,int,bool):# pragma: no cover abstract
        raise NotImplementedError
        
    async def apply_snapshot(self):# pragma: no cover abstract
        await self.log.install_snapshot()

@dataclass
class SnapShot:
    last_index:int
    last_term:int
    tool:Optional[SnapShotToolAPI] = field(default=None)

